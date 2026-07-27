import asyncio
from pipeline import InternNode, AtomicTask

prompts = [
    "What's the difference between a process and a thread?",
    "Add input validation to the signup form in `forms/signup.py` — email must be valid, password must be at least 8 characters.",
    "yo can u whip up smth that reads a csv and dumps it to json, python's fine"
]

def main():
    node = InternNode(model="nova3b:latest")
    
    for i, p in enumerate(prompts, 1):
        print(f"\n{'='*20} FRESH CASE {i} {'='*20}")
        print(f"PROMPT:\n{p}\n")
        
        task = AtomicTask(id=i, description=p, expected_files=0)
        
        try:
            result = node.execute(task)
            print("RAW PIPELINE OUTPUT:")
            print(result.response.raw_text)
        except Exception as e:
            print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    main()
