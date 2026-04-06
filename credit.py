from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import json



class CreditUtilizationError(Exception): pass
class InvalidCardError(CreditUtilizationError): pass
class DuplicateCardError(CreditUtilizationError): pass


@dataclass
class Card:
    card_id: str
    limit: float
    balance: float

    def __post_init__(self):
        if not str(self.card_id).strip():
            raise InvalidCardError("card_id must be a non-empty string.")
        if self.limit < 0:
            raise InvalidCardError(f"[{self.card_id}] 'limit' must be non-negative.")
        if self.balance < 0:
            raise InvalidCardError(f"[{self.card_id}] 'balance' must be non-negative.")


@dataclass
class CardResult:
    card_id: str
    utilization: float
    risk: str


@dataclass
class UtilizationReport:
    per_card: List[CardResult]
    overall_utilization: float
    overall_risk: str

    def to_dict(self) -> dict:
        return {
            "per_card": [
                {
                    "card_id":     c.card_id,
                    "utilization": c.utilization,
                    "risk":        c.risk,
                }
                for c in self.per_card
            ],
            "overall_utilization": self.overall_utilization,
            "overall_risk":        self.overall_risk,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class CreditUtilizationEngine:

    def calculate(self, payload: dict) -> UtilizationReport:
        cards_data = self._extract_cards(payload)
        cards      = self._parse_and_validate(cards_data)

        per_card_results = [self._process_card(c) for c in cards]

        total_balance = sum(c.balance for c in cards)
        total_limit   = sum(c.limit   for c in cards)
        overall_util  = self._compute_utilization(total_balance, total_limit)
        overall_risk  = self._assign_risk(overall_util)

        return UtilizationReport(
            per_card            = per_card_results,
            overall_utilization = overall_util,
            overall_risk        = overall_risk,
        )

    def _extract_cards(self, payload: dict) -> list:
        if not isinstance(payload, dict):
            raise CreditUtilizationError("Payload must be a dict.")
        if "cards" not in payload:
            raise CreditUtilizationError("Missing required key: 'cards'.")
        if not isinstance(payload["cards"], list) or len(payload["cards"]) == 0:
            raise CreditUtilizationError("'cards' must be a non-empty list.")
        return payload["cards"]

    def _parse_and_validate(self, cards_data: list) -> List[Card]:
        seen_ids = set()
        cards    = []
        for idx, item in enumerate(cards_data):
            card_id = item.get("card_id", f"<index {idx}>")
            if card_id in seen_ids:
                raise DuplicateCardError(f"Duplicate card_id: '{card_id}'.")
            seen_ids.add(card_id)
            limit   = item.get("limit")
            balance = item.get("balance")
            if limit is None:
                raise InvalidCardError(f"[{card_id}] Missing field: 'limit'.")
            if balance is None:
                raise InvalidCardError(f"[{card_id}] Missing field: 'balance'.")
            cards.append(Card(card_id=str(card_id), limit=float(limit), balance=float(balance)))
        return cards

    def _process_card(self, card: Card) -> CardResult:
        util = self._compute_utilization(card.balance, card.limit)
        return CardResult(
            card_id     = card.card_id,
            utilization = util,
            risk        = self._assign_risk(util),
        )

    @staticmethod
    def _compute_utilization(balance: float, limit: float) -> float:
        if limit == 0:
            return 1.0
        return round(balance / limit, 3)

    @staticmethod
    def _assign_risk(utilization: float) -> str:
        if utilization < 0.30:
            return "Low"
        elif utilization <= 0.70:
            return "Medium"
        else:
            return "High"



def calculate_credit_utilization(payload: dict) -> dict:
    engine = CreditUtilizationEngine()
    report = engine.calculate(payload)
    return report.to_dict()




def create_app():
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        raise ImportError("Run: pip install flask")

    app = Flask(__name__)

    @app.route("/calculate-utilization", methods=["POST"])
    def calculate():
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415
        try:
            result = calculate_credit_utilization(request.get_json())
            return jsonify(result), 200
        except (InvalidCardError, DuplicateCardError, CreditUtilizationError) as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": "Internal server error", "detail": str(e)}), 500

    return app




if __name__ == "__main__":
    import sys

    payload = {
        "cards": [
            {"card_id": "A", "limit": 100000, "balance": 25000},
            {"card_id": "B", "limit": 50000,  "balance": 30000},
        ]
    }

    result = calculate_credit_utilization(payload)
    print(json.dumps(result, indent=2))

    if "--serve" in sys.argv:
        print("\nStarting Flask API on http://localhost:5000 ...")
        create_app().run(debug=True, port=5000)
