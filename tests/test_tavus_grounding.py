from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GROUNDING_FILE = REPO_ROOT / "services" / "teams-media-bot" / "config" / "parlayvu-avatar-grounding.md"
TAVUS_SPIKE = REPO_ROOT / "services" / "teams-media-bot" / "scripts" / "Invoke-TavusSpike.ps1"


def test_grounding_context_contains_authoritative_parlayvu_facts():
    context = GROUNDING_FILE.read_text(encoding="utf-8")

    assert "ParlayVU.ai" in context
    assert "Blake Quinn: Intelligence and Insights" in context
    assert "Morgan Patel: Paid Media" in context
    assert "No canonical Maya team role was found" in context
    assert "Tavus conversations are provider-hosted avatar sessions today" in context
    assert "parlayvu.com" in context


def test_tavus_spike_injects_grounding_into_conversational_context():
    script = TAVUS_SPIKE.read_text(encoding="utf-8")

    assert "parlayvu-avatar-grounding.md" in script
    assert "Get-Content -LiteralPath $resolvedGroundingPath -Raw" in script
    assert "ParlayVU project memory and the grounding context below override" in script
    assert "conversational_context = $conversationalContext" in script
    assert "ParlayVU.ai, not parlayvu.com" in script
    assert "No canonical ParlayVU role for Maya" in script
