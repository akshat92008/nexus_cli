# 🚀 Simple 3-Step Guide to Fine-Tune Your Custom Model for Free

Follow these 3 simple steps to fine-tune your custom model on a free Google NVIDIA T4 GPU:

---

### Step 1: Open Google Colab
1. Go to [colab.research.google.com](https://colab.research.google.com).
2. Click **New Notebook**.
3. In the top menu, click **Runtime** ➔ **Change runtime type** ➔ Select **T4 GPU** ➔ Click **Save**.

---

### Step 2: Upload Your Dataset & Script
1. On the left sidebar of Google Colab, click the **Folder Icon 📁** (Files).
2. Drag and drop these 2 files from your Desktop (`fable5-1.5gb` folder) into Colab:
   - `dataset_fable5.jsonl`
   - `colab_training.py`

---

### Step 3: Run Training & Download Your Model
In the Colab code cell, paste this single line and press **Shift + Enter**:

```bash
!python colab_training.py
```

- Training takes **~10-15 minutes**.
- Once complete, a file named `jarvis-fable5-1.5b-q4_k_m.gguf` will appear in Colab's file folder on the left.
- Right-click `jarvis-fable5-1.5b-q4_k_m.gguf` and select **Download**.
- Move the downloaded file into your Desktop folder: `/Users/ashishsingh/Desktop/fable5-1.5gb/models/jarvis-fable5-1.5b/`.

---

🎉 **Done!** Your desktop launcher (`Launch_Fable_Engine.command`) will now instantly run **YOUR OWN CUSTOM FINE-TUNED AI MODEL**!
