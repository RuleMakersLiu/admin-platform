package kafka

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/IBM/sarama"
	"github.com/spf13/viper"
)

// Producer Kafka生产者
type Producer struct {
	producer    sarama.AsyncProducer
	topic       string
	queue       chan []byte
	queueSize   int
	batchSize   int
	flushPeriod time.Duration
	wg          sync.WaitGroup
	ctx         context.Context
	cancel      context.CancelFunc

	// 统计信息
	processedCount int64
	failedCount    int64
	lastProcessAt  time.Time
	mu             sync.RWMutex
}

var (
	producerInstance *Producer
	once             sync.Once
)

// GetProducer 获取Kafka生产者单例
func GetProducer() *Producer {
	once.Do(func() {
		producerInstance = &Producer{
			topic:       viper.GetString("kafka.topic"),
			queue:       make(chan []byte, viper.GetInt("kafka.queue_size")),
			queueSize:   viper.GetInt("kafka.queue_size"),
			batchSize:   viper.GetInt("kafka.batch_size"),
			flushPeriod: time.Duration(viper.GetInt("kafka.flush_period_ms")) * time.Millisecond,
		}
	})
	return producerInstance
}

// Connect 连接到Kafka
func (p *Producer) Connect() error {
	config := sarama.NewConfig()
	config.Producer.RequiredAcks = sarama.WaitForLocal
	config.Producer.Compression = sarama.CompressionSnappy
	config.Producer.Flush.Frequency = 100 * time.Millisecond
	config.Producer.Flush.Bytes = 1024 * 1024 // 1MB
	config.Producer.Retry.Max = 5
	config.Producer.Retry.Backoff = 100 * time.Millisecond

	brokers := viper.GetStringSlice("kafka.brokers")
	if len(brokers) == 0 {
		return fmt.Errorf("kafka brokers not configured")
	}

	producer, err := sarama.NewAsyncProducer(brokers, config)
	if err != nil {
		return fmt.Errorf("failed to create kafka producer: %w", err)
	}

	p.producer = producer
	p.ctx, p.cancel = context.WithCancel(context.Background())

	// 启动后台处理协程
	p.wg.Add(2)
	go p.processQueue()
	go p.handleErrors()

	log.Printf("[Kafka] Producer connected to %v, topic: %s", brokers, p.topic)
	return nil
}

// Send 发送事件到队列
func (p *Producer) Send(data interface{}) error {
	jsonData, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal data: %w", err)
	}

	select {
	case p.queue <- jsonData:
		return nil
	default:
		return fmt.Errorf("queue is full")
	}
}

// processQueue 处理队列中的消息
func (p *Producer) processQueue() {
	defer p.wg.Done()

	batch := make([][]byte, 0, p.batchSize)
	ticker := time.NewTicker(p.flushPeriod)
	defer ticker.Stop()

	flush := func() {
		if len(batch) == 0 {
			return
		}

		for _, data := range batch {
			msg := &sarama.ProducerMessage{
				Topic: p.topic,
				Value: sarama.ByteEncoder(data),
			}
			p.producer.Input() <- msg
		}

		p.mu.Lock()
		p.processedCount += int64(len(batch))
		p.lastProcessAt = time.Now()
		p.mu.Unlock()

		batch = batch[:0]
	}

	for {
		select {
		case <-p.ctx.Done():
			// 关闭前刷新剩余消息
			flush()
			return

		case data := <-p.queue:
			batch = append(batch, data)
			if len(batch) >= p.batchSize {
				flush()
			}

		case <-ticker.C:
			flush()
		}
	}
}

// handleErrors 处理发送错误
func (p *Producer) handleErrors() {
	defer p.wg.Done()

	for {
		select {
		case <-p.ctx.Done():
			return
		case err := <-p.producer.Errors():
			if err != nil {
				p.mu.Lock()
				p.failedCount++
				p.mu.Unlock()
				log.Printf("[Kafka] Failed to send message: %v", err)
			}
		}
	}
}

// Close 关闭生产者
func (p *Producer) Close() error {
	if p.cancel != nil {
		p.cancel()
	}
	p.wg.Wait()

	if p.producer != nil {
		return p.producer.Close()
	}
	return nil
}

// IsConnected 检查连接状态
func (p *Producer) IsConnected() bool {
	return p.producer != nil
}

// GetStats 获取统计信息
func (p *Producer) GetStats() (queueSize int, processedCount int64, failedCount int64, lastProcessAt time.Time) {
	p.mu.RLock()
	defer p.mu.RUnlock()

	return len(p.queue), p.processedCount, p.failedCount, p.lastProcessAt
}

// HealthCheck 健康检查
func (p *Producer) HealthCheck() error {
	if !p.IsConnected() {
		return fmt.Errorf("kafka producer not connected")
	}
	return nil
}
