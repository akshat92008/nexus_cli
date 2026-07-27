import sys
try:
    from fpdf import FPDF
except ImportError:
    print("fpdf2 is not installed.")
    sys.exit(1)

class PDFReport(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 15)
        # Header title
        self.cell(0, 10, 'NOVA 1.5b: MODEL SPECIFICATION & CAPABILITIES REPORT', 0, 1, 'C')
        self.set_font('Helvetica', 'I', 10)
        self.cell(0, 10, 'Developed by Amuara Labs', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Helvetica', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, body):
        self.set_font('Helvetica', '', 11)
        self.multi_cell(0, 7, body)
        self.ln(5)

    def add_section(self, title, body):
        self.chapter_title(title)
        self.chapter_body(body)


def generate_report():
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    content = [
        ("1. Model Overview", 
         "Nova 1.5b is a state-of-the-art, open-weight AI software engineering model. Designed specifically to rival proprietary frontier models like Claude Fable 5 and Kimi K3, Nova abandons the traditional 'next-token prediction' approach in favor of Execution-Guided Reasoning.\n\n"
         "Built to run entirely offline on consumer hardware (e.g., Apple Silicon with 8GB RAM), Nova 1.5b packs the architectural reasoning of a much larger model into a highly efficient 1.5-billion parameter footprint through the use of Test-Time Compute (TTC) and autonomous multi-agent orchestration."
        ),
        ("2. Core Strengths: What Nova 1.5b Excels At", 
         "Nova 1.5b is highly specialized for software engineering. Its primary strengths are:\n\n"
         "A. Complex Problem Solving via Test-Time Compute (TTC)\n"
         "Nova uses Monte Carlo Tree Search (MCTS) to generate multiple potential solutions to a problem. It then executes these solutions in a secure sandbox. If a solution encounters a SyntaxError or AssertionError, Nova automatically backtracks, reads the error, and self-heals the code before presenting the final answer.\n\n"
         "B. Multi-File Repository Refactoring\n"
         "Nova 1.5b uses AST-Aware Retrieval (Abstract Syntax Tree). Instead of blindly reading files line-by-line, Nova understands the structure of the code, mapping dependencies between classes, functions, and modules across interconnected files in Python, Rust, Go, TypeScript, and C++.\n\n"
         "C. Zero-Fabrication Code Generation\n"
         "Nova learns through Group Relative Policy Optimization (GRPO). During training, it is only rewarded if its generated code compiles and passes unit tests in a real sandbox, heavily penalizing hallucinated APIs.\n\n"
         "D. Autonomous Auditing & Security Review\n"
         "Through its Hierarchical Multi-Agent Orchestration, Nova splits itself into specialized roles: an Architect to plan, a Coder to execute, and a Reviewer to audit the code for memory leaks, security vulnerabilities (like SQL injection or XSS), and edge cases."
        ),
        ("3. Key Architectural Innovations", 
         "1. The RLEF Loop (Reinforcement Learning from Execution Feedback)\n"
         "Nova continuously evaluates its own performance on unseen problems, identifies its weakest domains, and dynamically generates new training data to patch its knowledge gaps.\n\n"
         "2. Episodic Memory Rollbacks\n"
         "Nova maintains a local semantic vector database. Crucially, if Nova's multi-agent system goes down a flawed architectural path, it can perform an 'episodic rollback' (similar to a git reset), allowing it to try a new approach without poisoning its context window.\n\n"
         "3. Parametric Dataset Generation\n"
         "Nova was trained on 100,000+ highly diverse, synthetically generated tasks across 15 engineering domains. This exposes Nova to an immense variety of edge cases and constraints."
        ),
        ("4. Technical Specifications & Deployment", 
         "Nova 1.5b is engineered for maximum efficiency and privacy:\n\n"
         "- Parameters: 1.5 Billion\n"
         "- Quantization: GGUF (Q4_K_M) 4-bit precision\n"
         "- VRAM/RAM Requirement: ~1.18 GB (Runs easily on 8GB Unified Memory systems)\n"
         "- Deployment Target: Local execution on Apple Silicon (M1/M2/M3) and consumer NVIDIA GPUs\n"
         "- Privacy: 100% Offline. Zero telemetry, zero data collection. All inference, AST indexing, and sandboxed execution happens entirely on the local machine."
        ),
        ("5. Ideal Use Cases", 
         "Nova 1.5b is best deployed as a persistent local pair-programmer or background agent:\n\n"
         "- Offline CI/CD Auditing: Reviewing pull requests locally for security flaws and logical errors without uploading code to third-party servers.\n"
         "- Legacy Codebase Modernization: Pointing Nova at a large, undocumented repository and asking its Architect agent to map dependencies and plan a migration.\n"
         "- Autonomous Bug Fixing: Feeding a GitHub issue and a stack trace directly into Nova's Test-Time Compute engine to generate, test, and verify the patch autonomously."
        )
    ]

    for title, body in content:
        pdf.add_section(title, body)

    output_path = "Nova_1.5b_Model_Report.pdf"
    pdf.output(output_path)
    print(f"Successfully generated PDF: {output_path}")

if __name__ == "__main__":
    generate_report()
