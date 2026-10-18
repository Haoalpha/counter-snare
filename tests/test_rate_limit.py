"""Chứng minh tuân thủ rate limit BTC: không bao giờ vượt hạn mức RPM của từng model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import GEMMA, GLM52, GLM53, OFFICIAL_RPM, QWEN, ROUTES, RateLimiter  # noqa: E402


def test_official_limits_match_rules():
    assert OFFICIAL_RPM == {GLM52: 15, GLM53: 10, QWEN: 10, GEMMA: 15}


def test_limiter_never_exceeds_rpm():
    lim = RateLimiter(OFFICIAL_RPM)
    for model, rpm in OFFICIAL_RPM.items():
        granted = sum(lim.try_acquire(model) for _ in range(rpm * 3))
        assert granted == rpm - 1  # chừa 1 request an toàn
        assert lim.wait_time(model) > 0


def test_penalized_model_is_skipped():
    lim = RateLimiter(OFFICIAL_RPM)
    lim.penalize(QWEN, 30)
    assert not lim.try_acquire(QWEN)
    assert lim.try_acquire(GEMMA)


def test_every_route_uses_only_greennode_maas_models():
    for route in ROUTES.values():
        assert set(route) <= set(OFFICIAL_RPM)
