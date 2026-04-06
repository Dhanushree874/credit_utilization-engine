import json
from credit  import calculate_credit_utilization

def get_user_input():
    cards = []

    n = int(input("Enter number of cards: "))

    for i in range(n):
        print(f"\nEnter details for Card {i+1}")
        card_id = input("Card ID: ")
        limit = float(input("Limit: "))
        balance = float(input("Balance: "))

        cards.append({
            "card_id": card_id,
            "limit": limit,
            "balance": balance
        })

    return {"cards": cards}


def main():
    print("=== Credit Utilization Calculator ===")

    payload = get_user_input()

    try:
        result = calculate_credit_utilization(payload)
        print("\n✅ Result:")
        print(json.dumps(result, indent=2))

    except Exception as e:
        print("\n❌ Error:", str(e))


if __name__ == "__main__":
    main()