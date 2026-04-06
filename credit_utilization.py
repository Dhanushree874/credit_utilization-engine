




from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import json




RISK_THRESHOLDS = {
    "Low":    (0.0,  0.30),
    "Medium": (0.30, 0.70),
    "High":   (0.70, float("inf")),
}

RISK_TIPS = {
    "Low":    "Great shape! Keep utilization below 30% to maintain a healthy credit score.",
    "Medium": "Moderate risk. Try paying down balances to get below 30% utilization.",
    "High":   "High risk! High utilization significantly hurts your credit score. "
              "Prioritize paying down this balance immediately.",
}



class CreditUtilizationError(Exception):
    """Base exception for all Credit Utilization Engine errors."""


class InvalidCardError(CreditUtilizationError):
    """Raised when a card entry has invalid or missing data."""


class DuplicateCardError(CreditUtilizationError):
    """Raised when duplicate card IDs are detected."""



@dataclass
class Card:
    card_id: str
    limit: float
    balance: float

    def __post_init__(self):
        self._validate()

    def _validate(self):
        if not self.card_id or not str(self.card_id).strip():
            raise InvalidCardError("card_id must be a non-empty string.")

        if not isinstance(self.limit, (int, float)) or self.limit < 0:
            raise InvalidCardError(
                f"[{self.card_id}] 'limit' must be a non-negative number. Got: {self.limit}"
            )

        if not isinstance(self.balance, (int, float)) or self.balance < 0:
            raise InvalidCardError(
                f"[{self.card_id}] 'balance' must be a non-negative number. Got: {self.balance}"
            )

        if self.balance > self.limit and self.limit > 0:
            # Over-limit spending is possible (e.g. fees/interest) — warn but allow
            pass  # handled as a flag in result


@dataclass
class CardResult:
    card_id: str
    limit: float
    balance: float
    utilization: float          # ratio, e.g. 0.25 = 25%
    utilization_pct: str        # human-readable, e.g. "25.00%"
    risk: str
    tip: str
    over_limit: bool = False    # True if balance > limit


@dataclass
class UtilizationReport:
    per_card: List[CardResult]
    overall_utilization: float
    overall_utilization_pct: str
    overall_risk: str
    overall_tip: str
    total_balance: float
    total_limit: float
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a clean JSON-compatible dictionary."""
        return {
            "per_card": [
                {
                    "card_id":          c.card_id,
                    "limit":            c.limit,
                    "balance":          c.balance,
                    "utilization":      round(c.utilization, 4),
                    "utilization_pct":  c.utilization_pct,
                    "risk":             c.risk,
                    "tip":              c.tip,
                    "over_limit":       c.over_limit,
                }
                for c in self.per_card
            ],
            "overall_utilization":     round(self.overall_utilization, 4),
            "overall_utilization_pct": self.overall_utilization_pct,
            "overall_risk":            self.overall_risk,
            "overall_tip":             self.overall_tip,
            "total_balance":           self.total_balance,
            "total_limit":             self.total_limit,
            "warnings":                self.warnings,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)




class CreditUtilizationEngine:
    """
    Production-grade credit utilization calculator.

    Usage
    -----
        engine = CreditUtilizationEngine()
        report = engine.calculate(payload)
        print(report.to_json())
    """

    def calculate(self, payload: dict) -> UtilizationReport:
        """
        Main entry point.

        Parameters
        ----------
        payload : dict
            Must contain a "cards" key with a list of card objects.
            Each card: {"card_id": str, "limit": number, "balance": number}

        Returns
        -------
        UtilizationReport
        """
        cards_data = self._extract_cards(payload)
        cards      = self._parse_and_validate(cards_data)
        warnings   = self._collect_warnings(cards)

        per_card_results  = [self._process_card(c) for c in cards]
        overall_util, overall_risk = self._compute_overall(cards)
        total_balance = sum(c.balance for c in cards)
        total_limit   = sum(c.limit   for c in cards)

        return UtilizationReport(
            per_card               = per_card_results,
            overall_utilization    = overall_util,
            overall_utilization_pct= self._fmt_pct(overall_util),
            overall_risk           = overall_risk,
            overall_tip            = RISK_TIPS[overall_risk],
            total_balance          = total_balance,
            total_limit            = total_limit,
            warnings               = warnings,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_cards(self, payload: dict) -> list:
        if not isinstance(payload, dict):
            raise CreditUtilizationError("Payload must be a JSON object / dict.")
        if "cards" not in payload:
            raise CreditUtilizationError("Missing required key: 'cards'.")
        if not isinstance(payload["cards"], list):
            raise CreditUtilizationError("'cards' must be a list.")
        if len(payload["cards"]) == 0:
            raise CreditUtilizationError("'cards' list is empty. Provide at least one card.")
        return payload["cards"]

    def _parse_and_validate(self, cards_data: list) -> List[Card]:
        seen_ids = set()
        cards: List[Card] = []

        for idx, item in enumerate(cards_data):
            if not isinstance(item, dict):
                raise InvalidCardError(f"Card at index {idx} must be an object/dict.")

            # Fill defaults so error messages are meaningful
            card_id = item.get("card_id", f"<index {idx}>")

            if card_id in seen_ids:
                raise DuplicateCardError(f"Duplicate card_id detected: '{card_id}'.")
            seen_ids.add(card_id)

            limit   = item.get("limit")
            balance = item.get("balance")

            if limit is None:
                raise InvalidCardError(f"[{card_id}] Missing required field: 'limit'.")
            if balance is None:
                raise InvalidCardError(f"[{card_id}] Missing required field: 'balance'.")

            cards.append(Card(card_id=str(card_id), limit=float(limit), balance=float(balance)))

        return cards

    def _collect_warnings(self, cards: List[Card]) -> List[str]:
        warnings = []
        for c in cards:
            if c.limit == 0:
                warnings.append(
                    f"Card '{c.card_id}' has a zero credit limit. "
                    "Utilization cannot be computed; it will be treated as 100% (High risk)."
                )
            if c.balance > c.limit and c.limit > 0:
                warnings.append(
                    f"Card '{c.card_id}' balance (${c.balance:,.2f}) exceeds its limit "
                    f"(${c.limit:,.2f}). This may indicate over-limit spending or accrued fees."
                )
        return warnings

    def _process_card(self, card: Card) -> CardResult:
        util      = self._compute_utilization(card.balance, card.limit)
        risk      = self._assign_risk(util)
        over_limit = card.balance > card.limit and card.limit > 0

        return CardResult(
            card_id         = card.card_id,
            limit           = card.limit,
            balance         = card.balance,
            utilization     = util,
            utilization_pct = self._fmt_pct(util),
            risk            = risk,
            tip             = RISK_TIPS[risk],
            over_limit      = over_limit,
        )

    def _compute_overall(self, cards: List[Card]):
        total_balance = sum(c.balance for c in cards)
        total_limit   = sum(c.limit   for c in cards)
        util          = self._compute_utilization(total_balance, total_limit)
        risk          = self._assign_risk(util)
        return util, risk

    @staticmethod
    def _compute_utilization(balance: float, limit: float) -> float:
        """
        Returns a utilization ratio in [0, ∞).
        If limit is 0, returns 1.0 (treated as fully utilized / High risk).
        """
        if limit == 0:
            return 1.0   # No credit available → treat as maxed out
        return balance / limit

    @staticmethod
    def _assign_risk(utilization: float) -> str:
        if utilization < 0.30:
            return "Low"
        elif utilization <= 0.70:
            return "Medium"
        else:
            return "High"

    @staticmethod
    def _fmt_pct(ratio: float) -> str:
        return f"{ratio * 100:.2f}%"


# ---------------------------------------------------------------------------
# Convenience function (matches the problem statement's function-style API)
# ---------------------------------------------------------------------------

def calculate_credit_utilization(payload: dict) -> dict:
    """
    Thin wrapper around CreditUtilizationEngine for quick/direct usage.

    Parameters
    ----------
    payload : dict  — same schema as problem statement

    Returns
    -------
    dict — JSON-serializable result matching expected output schema
    """
    engine = CreditUtilizationEngine()
    report = engine.calculate(payload)
    return report.to_dict()


# ---------------------------------------------------------------------------
# Flask REST API  (optional — run this file directly to start the server)
# ---------------------------------------------------------------------------

def create_app():
    """
    Creates a minimal Flask app exposing POST /calculate-utilization.
    Install Flask:  pip install flask
    """
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        raise ImportError("Flask is not installed. Run: pip install flask")

    app = Flask(__name__)

    @app.route("/calculate-utilization", methods=["POST"])
    def calculate():
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415

        try:
            payload = request.get_json()
            result  = calculate_credit_utilization(payload)
            return jsonify(result), 200

        except (InvalidCardError, DuplicateCardError, CreditUtilizationError) as exc:
            return jsonify({"error": str(exc)}), 400

        except Exception as exc:
            return jsonify({"error": "Internal server error", "detail": str(exc)}), 500

    return app


# ---------------------------------------------------------------------------
# CLI / Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # ── Demo mode ──────────────────────────────────────────────────────────
    sample_payload = {
        "cards": [
            {"card_id": "A", "limit": 100000, "balance": 25000},
            {"card_id": "B", "limit": 50000,  "balance": 30000},
        ]
    }

    print("=" * 60)
    print("  Credit Utilization Engine — Demo")
    print("=" * 60)

    result = calculate_credit_utilization(sample_payload)
    print(json.dumps(result, indent=2))

    # ── Edge-case tests ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Edge Cases")
    print("=" * 60)

    edge_cases = [
        ("Zero limit card", {
            "cards": [{"card_id": "Z", "limit": 0, "balance": 0}]
        }),
        ("Over-limit card", {
            "cards": [{"card_id": "X", "limit": 10000, "balance": 11000}]
        }),
        ("All zeroes", {
            "cards": [{"card_id": "Y", "limit": 0, "balance": 0},
                      {"card_id": "W", "limit": 0, "balance": 0}]
        }),
    ]

    for label, payload in edge_cases:
        print(f"\n→ {label}:")
        try:
            print(json.dumps(calculate_credit_utilization(payload), indent=2))
        except CreditUtilizationError as e:
            print(f"  CreditUtilizationError: {e}")

    # ── Flask server mode ──────────────────────────────────────────────────
    if "--serve" in sys.argv:
        print("\nStarting Flask API on http://localhost:5000 …")
        app = create_app()
        app.run(debug=True, port=5000)