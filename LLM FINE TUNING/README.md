# LLM Fine-Tuning — Mistral-7B with QLoRA

Fine-tuning **Mistral-7B-v0.1** on the **Databricks Dolly-15k** instruction-following dataset using **QLoRA** (4-bit quantization + Low-Rank Adaptation). The goal is to adapt a general-purpose language model to follow structured instructions more precisely and concisely.

This project explores *how* LLMs learn — specifically how a small fraction of updated parameters can produce large changes in output quality.

---

## Results

| Metric | Base Mistral-7B | Fine-tuned | Improvement |
|---|---|---|---|
| BLEU-1 | 0.177 | 0.428 | **+141.9%** |
| BLEU-2 | 0.047 | 0.176 | **+277.4%** |
| BLEU-4 | 0.038 | 0.088 | **+130.3%** |
| ROUGE-1 | 0.212 | 0.406 | **+91.1%** |
| ROUGE-2 | 0.069 | 0.208 | **+203.6%** |
| ROUGE-L | 0.143 | 0.333 | **+133.0%** |

Evaluated on 200 held-out examples from the Dolly-15k test split.

---

## What is QLoRA?

Training a full 7B-parameter model requires ~28 GB of GPU VRAM. QLoRA makes this feasible on a single GPU by combining two techniques:

1. **4-bit Quantization** — Load the base model weights in 4-bit precision (via `bitsandbytes`), reducing VRAM from ~28 GB to ~4 GB
2. **LoRA (Low-Rank Adaptation)** — Instead of updating all 3.7B parameters, inject small trainable "adapter" matrices into the attention layers

**In this run:**
- Total parameters: 3,766,071,296 (3.7B)
- Trainable LoRA parameters: 13,631,488 (13.6M)
- Trainable fraction: **0.362%**

Only 0.36% of the model's weights are updated during training — everything else stays frozen.

---

## Dataset — Dolly-15k

- **Source:** `databricks/databricks-dolly-15k` (HuggingFace)
- **Size:** 15,011 examples → 14,260 train / 751 test
- **Format:** Instruction-following pairs (instruction, optional context, response)
- **Categories:** Open Q&A, summarization, information extraction, code generation, creative writing, classification

Training prompt template:
```
### Instruction:
{instruction}

### Input:
{context}

### Response:
{response}
```

---

## Hyperparameters

| Parameter | Value |
|---|---|
| Base model | `mistralai/Mistral-7B-v0.1` |
| Quantization | 4-bit (NF4, double quant) |
| LoRA rank (r) | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.05 |
| Target modules | `q_proj`, `k_proj`, `v_proj`, `o_proj` |
| Epochs | 3 |
| Batch size | 8 (effective 16 with grad accumulation) |
| Learning rate | 2e-4 |
| LR scheduler | Cosine (3% warmup) |
| Optimizer | `paged_adamw_8bit` |
| Max sequence length | 1024 tokens |

---

## Qualitative Examples

The fine-tuned model produces shorter, more format-compliant, and more relevant responses:

**Code generation**
- Base: 560+ tokens with extensive comments and examples
- Fine-tuned: 16 tokens — a clean, correct palindrome function

**Summarization (2-sentence constraint)**
- Base: writes 3 sentences
- Fine-tuned: exactly 2 sentences

**Information retrieval (list format)**
- Base: narrative explanation
- Fine-tuned: clean bullet list

---

## Tech Stack

| Component | Library | Version |
|---|---|---|
| Model loading | `transformers` | 4.46.3 |
| Quantization | `bitsandbytes` | 0.46.1 |
| LoRA adapters | `peft` | 0.13.2 |
| Training loop | `trl` (SFTTrainer) | 0.12.0 |
| Distributed utils | `accelerate` | 1.1.1 |
| Dataset | `datasets` | 3.1.0 |
| Metrics | `evaluate` (BLEU, ROUGE) | 0.4.3 |
| Deep learning | `PyTorch` | 2.8.0+cu128 |

---

## Running the Notebook

### Hardware Requirements
- GPU with ≥ 16 GB VRAM (tested on NVIDIA L40S — 47.7 GB)
- CUDA 12.8+
- Estimated training time: ~80 min on L40S, ~25-30 min on A100

### Recommended Platform
**Lightning AI Studio** — provides managed GPU access with pre-configured CUDA environments.

1. Create a new Studio on [lightning.ai](https://lightning.ai)
2. Select **L40S** or **A100** GPU
3. Upload `LLM_FineTuning.ipynb`
4. Run all cells top-to-bottom

### Local Setup (if you have a compatible GPU)

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install transformers peft trl accelerate bitsandbytes datasets evaluate matplotlib seaborn
```

Then open and run `LLM_FineTuning.ipynb`.

---

## Notebook Structure

| Cell | Purpose |
|---|---|
| 0 | Verify GPU (`nvidia-smi`, PyTorch CUDA check) |
| 1 | Install dependencies |
| 2 | Verify all libraries loaded correctly |
| 3 | HuggingFace login (optional for gated models) |
| 4 | Define all hyperparameters |
| 5 | Load Mistral-7B in 4-bit QLoRA quantization |
| 6 | Load and format Dolly-15k dataset |
| 7 | Attach LoRA adapters to attention layers |
| 8 | **Fine-tune with SFTTrainer** (~80 min) |
| 9 | Reload models for clean evaluation |
| 10 | Generation helper function |
| 11 | Qualitative comparison on 5 diverse tasks |
| 12 | **Quantitative evaluation** — BLEU/ROUGE on 200 samples |
| 13 | Save results + zip LoRA adapter weights |
| B–F | Visualization: training curves, metrics bar charts, improvement % |

---

## Files

```
LLM FINE TUNING/
├── LLM_FineTuning.ipynb          # Complete fine-tuning pipeline
└── LLM_FineTuning_printable.pdf  # PDF export for reference
```

---

## Key Takeaways

- QLoRA makes 7B model fine-tuning accessible on a single consumer/research GPU
- 0.36% trainable parameters is enough to meaningfully shift model behaviour
- The model learns to be *more concise* and *more format-compliant*, not just more accurate
- BLEU-2 improvement (+277%) is the strongest signal — the model learns better bigram patterns, indicating improved coherence and phrasing
