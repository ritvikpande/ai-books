from rate_limit import RateLimiter


def test_allows_up_to_the_limit_then_rejects():
    limiter = RateLimiter(limit=3, window_seconds=60)
    assert limiter.allow("a", now=0) is True
    assert limiter.allow("a", now=0) is True
    assert limiter.allow("a", now=0) is True
    assert limiter.allow("a", now=0) is False


def test_rejecting_does_not_consume_budget():
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.allow("a", now=0) is True
    assert limiter.allow("a", now=0) is False
    assert limiter.allow("a", now=0) is False  # still rejected, not "used up" further


def test_different_keys_have_independent_budgets():
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.allow("a", now=0) is True
    assert limiter.allow("b", now=0) is True
    assert limiter.allow("a", now=0) is False
    assert limiter.allow("b", now=0) is False


def test_old_hits_expire_out_of_the_window():
    limiter = RateLimiter(limit=1, window_seconds=10)
    assert limiter.allow("a", now=0) is True
    assert limiter.allow("a", now=9.999) is False  # still inside the 10s window
    assert limiter.allow("a", now=10) is True      # exactly 10s later -> expired
