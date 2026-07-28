from pipeline import InternNode, AtomicTask

prompts = [
    "Write a Python script `src/metrics.py` that parses a CSV file and calculates the 95th percentile of the 'latency' column.",
    "Create a function in `utils/math.py` that calculates the factorial of a number iteratively.",
    "Implement a REST endpoint in `app.py` using Flask that returns the current UTC time in ISO format.",
    "Write a bash script `backup.sh` that zips the `/data` directory and moves it to `/backup`."
]

def run_tests():
    node = InternNode(model="nova3b:latest")
    
    for i, p in enumerate(prompts, 1):
        print(f"\n==================== REGRESSION CASE A{i} ====================")
        print(f"PROMPT:\n{p}\n")
        
        task = AtomicTask(id=i, description=p, expected_files=0)
        result = node.execute(task)
        print("RAW PIPELINE OUTPUT:")
        print(result.response.raw_text)
        print("\n")

if __name__ == "__main__":
    run_tests()
