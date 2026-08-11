package budget

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestBudgetExceedAndRevocation(t *testing.T) {
	store := NewMemoryStore()
	ctx := context.Background()
	if _, _, err := store.Charge(ctx, "jti", 0.4, 2, 1, time.Minute); err != nil {
		t.Fatal(err)
	}
	if _, _, err := store.Charge(ctx, "jti", 0.4, 2, 1, time.Minute); err != nil {
		t.Fatal(err)
	}
	if _, _, err := store.Charge(ctx, "jti", 0.1, 2, 1, time.Minute); !errors.Is(err, ErrExceeded) {
		t.Fatalf("expected call budget exceeded, got %v", err)
	}
	if err := store.Revoke(ctx, "other", time.Minute); err != nil {
		t.Fatal(err)
	}
	if _, _, err := store.Charge(ctx, "other", 0.1, 2, 1, time.Minute); err == nil {
		t.Fatal("expected revoked token rejection")
	}
}
