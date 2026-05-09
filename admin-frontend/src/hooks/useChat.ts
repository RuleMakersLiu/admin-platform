import { useState, useEffect, useCallback, useRef } from 'react';
import { useChatStore } from '@/stores/chat';

// 防抖 Hook
export const useDebounce = <T>(value: T, delay: number = 300): T => {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
};

// 搜索 Hook (带防抖)
export const useSearch = (delay: number = 300) => {
  const [keyword, setKeyword] = useState('');
  const debouncedKeyword = useDebounce(keyword, delay);

  return {
    keyword,
    setKeyword,
    debouncedKeyword,
    clearKeyword: () => setKeyword(''),
  };
};

// 主题切换 Hook
export const useThemeSwitch = () => {
  const { theme, setTheme, toggleTheme } = useChatStore();

  // 应用主题到 document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.body.className = theme === 'dark' ? 'dark-theme' : 'light-theme';
  }, [theme]);

  // 监听系统主题变化
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const handleChange = () => {
      // 可选：自动跟随系统主题
      // setTheme(e.matches ? 'dark' : 'light');
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  return {
    theme,
    setTheme,
    toggleTheme,
    isDark: theme === 'dark',
  };
};

// 滚动到底部 Hook
export const useScrollToBottom = (dependency: any[]) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, dependency);

  const scrollToBottom = useCallback((smooth = true) => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: smooth ? 'smooth' : 'auto',
      });
    }
  }, []);

  return { containerRef, scrollToBottom };
};

// 键盘快捷键 Hook
export const useKeyboardShortcut = (
  key: string,
  callback: () => void,
  modifiers: { ctrl?: boolean; shift?: boolean; alt?: boolean } = {}
) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const ctrlMatch = modifiers.ctrl ? e.ctrlKey || e.metaKey : true;
      const shiftMatch = modifiers.shift ? e.shiftKey : true;
      const altMatch = modifiers.alt ? e.altKey : true;

      if (e.key.toLowerCase() === key.toLowerCase() && ctrlMatch && shiftMatch && altMatch) {
        e.preventDefault();
        callback();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [key, callback, modifiers]);
};

// 本地存储 Hook
export const useLocalStorage = <T>(key: string, initialValue: T) => {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch (error) {
      console.error(`Error reading localStorage key "${key}":`, error);
      return initialValue;
    }
  });

  const setValue = useCallback(
    (value: T | ((val: T) => T)) => {
      try {
        const valueToStore = value instanceof Function ? value(storedValue) : value;
        setStoredValue(valueToStore);
        window.localStorage.setItem(key, JSON.stringify(valueToStore));
      } catch (error) {
        console.error(`Error setting localStorage key "${key}":`, error);
      }
    },
    [key, storedValue]
  );

  return [storedValue, setValue] as const;
};

// 窗口大小 Hook
export const useWindowSize = () => {
  const [size, setSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });

  useEffect(() => {
    const handleResize = () => {
      setSize({
        width: window.innerWidth,
        height: window.innerHeight,
      });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return size;
};

// 响应式布局 Hook
export const useResponsive = () => {
  const { width } = useWindowSize();

  return {
    isMobile: width < 768,
    isTablet: width >= 768 && width < 1024,
    isDesktop: width >= 1024,
    isLargeDesktop: width >= 1440,
  };
};

// 自动生成 ID Hook
export const useId = (prefix: string = 'id') => {
  const idRef = useRef(0);

  return useCallback(() => {
    idRef.current += 1;
    return `${prefix}_${Date.now()}_${idRef.current}`;
  }, [prefix]);
};

// 剪贴板 Hook
export const useClipboard = () => {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      return true;
    } catch (error) {
      console.error('Failed to copy:', error);
      return false;
    }
  }, []);

  return { copy, copied };
};
