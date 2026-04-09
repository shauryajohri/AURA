from core.brain import process

print("AURA Backend Test — type 'quit' to exit\n")

while True:
    user_input = input("You: ").strip()
    if user_input.lower() == "quit":
        print("[AURA] Shutting down.")
        break
    if not user_input:
        continue

    response = process(user_input)
    print(f"\nAURA: {response}\n")