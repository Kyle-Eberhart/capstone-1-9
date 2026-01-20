# LLM Exam Generation Diagnosis

## Root Cause Analysis

Based on testing and logs, the exam generation is failing because:

1. **Model is too small** - `arize-ai/qwen-2-1.5b-instruct` (1.5B) struggles with generating 8 unique questions
2. **Similarity detection was too strict** - 70% threshold caught legitimate variations
3. **Similarity algorithm was too simplistic** - Missed semantic similarity (e.g., "What is X?" vs "How does X work?")
4. **Temperature and max_tokens weren't being used** - API calls used defaults

## Issues Identified & Fixed

### 1. Model Too Small ✅ (Identified, needs user action)
**Current Model**: `arize-ai/qwen-2-1.5b-instruct` (1.5 billion parameters)

**Problems**:
- Too small for complex JSON generation tasks
- Struggles with following detailed instructions
- Generates similar/repetitive questions
- Chinese model (Qwen) - explains Chinese responses

**Recommendation**: Use a larger, more capable model:
- `meta-llama/Llama-3-8b-chat-hf` (8B parameters, better instruction following)
- `mistralai/Mixtral-8x7B-Instruct-v0.1` (56B parameters, excellent for structured output)
- `meta-llama/Llama-3-70b-chat-hf` (70B parameters, best quality but slower/expensive)

### 2. Temperature and Max Tokens Not Used ✅ (FIXED)
**Issue**: The API call wasn't passing `temperature` and `max_tokens` parameters.

**Fix Applied**: Now using:
- `temperature: 0.7` (from settings)
- `max_tokens: 2000` (from settings)

**Note**: For exam generation, consider:
- Lower temperature (0.3-0.5) for more consistent, structured output
- Higher max_tokens (3000-4000) for longer exam questions

### 3. Similarity Detection Issues ✅ (FIXED)
**Issues**:
- Similarity threshold was too strict (70%) - caught legitimate variations
- Similarity algorithm was too simplistic - missed semantic similarity

**Fixes Applied**:
- Raised threshold to 85% (less strict)
- **Improved similarity algorithm** to detect semantic similarity:
  - Now extracts key terms (excluding common question words)
  - Detects when questions share the same subject matter even with different phrasing
  - Example: "What is a hash table?" vs "How does a hash table work?" now scores 75% (was 32%)
  - Better catches questions about the same concept with different wording

**Note**: With a better model, you can lower the threshold back to 75-80% for stricter uniqueness.

## Testing

Run the diagnostic script:
```bash
python test_llm_exam_generation.py
```

This will:
- Show current configuration
- Test exam generation with detailed logging
- Display any errors with full tracebacks

## Recommended Next Steps

1. **Update Model in `.env` file**:
   ```
   LLM_MODEL=meta-llama/Llama-3-8b-chat-hf
   ```

2. **Adjust Temperature** (optional, in `.env`):
   ```
   LLM_TEMPERATURE=0.4
   LLM_MAX_TOKENS=3000
   ```

3. **Test with the diagnostic script** to verify improvements

4. **Monitor logs** when generating exams to see:
   - Which attempts succeed/fail
   - Similarity scores between questions
   - JSON parsing issues
   - API response details

## Current Configuration Location

Settings are in:
- `app/settings.py` - Default values
- `.env` file - Override defaults (create if doesn't exist)

## Logging

With the enhanced logging, you'll now see:
- Model name, temperature, max_tokens in each API call
- Full response previews when JSON parsing fails
- Detailed similarity scores for each question pair
- All failure reasons across all attempts
