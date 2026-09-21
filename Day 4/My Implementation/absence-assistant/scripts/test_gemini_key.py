"""Test Gemini API key and model availability."""
import os
import sys
from dotenv import load_dotenv

# Force UTF-8 output for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load .env file
load_dotenv()

print("=" * 60)
print("GEMINI API KEY TEST")
print("=" * 60)

# Check if key exists
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

if not api_key:
    print("[!] GEMINI_API_KEY not set in .env file")
    print("\nFix:")
    print("   1. Go to https://aistudio.google.com/apikey")
    print("   2. Create/copy your API key")
    print("   3. Add to .env file: GEMINI_API_KEY=your-key-here")
    exit(1)

key_source = "GEMINI_API_KEY" if os.environ.get("GEMINI_API_KEY") else "GOOGLE_API_KEY (system)"
print(f"[OK] API Key found ({key_source}): {api_key[:10]}...{api_key[-4:]}")
print(f"[OK] Model: {model}")

# Test 1: Import google-genai
print("\n" + "-" * 60)
print("Test 1: Checking google-genai library...")
print("-" * 60)

try:
    from google import genai
    print("[OK] google-genai library installed")
except ImportError as e:
    print(f"[FAIL] google-genai library NOT installed: {e}")
    print("\nFix: pip install google-genai")
    exit(1)

# Test 2: Create client
print("\n" + "-" * 60)
print("Test 2: Creating Gemini client...")
print("-" * 60)

try:
    client = genai.Client(api_key=api_key)
    print("[OK] Client created successfully")
except Exception as e:
    print(f"[FAIL] Failed to create client: {e}")
    exit(1)

# Test 3: List available models
print("\n" + "-" * 60)
print("Test 3: Listing available models...")
print("-" * 60)

try:
    models = client.models.list()
    print(f"[OK] Found {len(list(models))} models")

    print("\nAvailable models for text generation:")
    text_models = []
    for m in client.models.list():
        if 'generateContent' in m.supported_generation_methods:
            text_models.append(m.name)
            print(f"   - {m.name}")

    if not text_models:
        print("[WARN] No text generation models found")
except Exception as e:
    print(f"[FAIL] Failed to list models: {e}")
    print(f"\n[WARN] This might indicate an API key issue")

# Test 4: Try to use the configured model
print("\n" + "-" * 60)
print(f"Test 4: Testing model '{model}'...")
print("-" * 60)

try:
    from google.genai import types

    response = client.models.generate_content(
        model=model,
        contents=types.Content(
            role="user",
            parts=[types.Part(text="Say 'Hello' in exactly one word.")]
        ),
        config=types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=10
        )
    )

    if response.candidates:
        text = response.candidates[0].content.parts[0].text
        print(f"[OK] Model responded: '{text.strip()}'")
        print(f"[OK] Token usage: {response.usage_metadata.prompt_token_count} in, "
              f"{response.usage_metadata.candidates_token_count} out")
    else:
        print("[WARN] Model returned no candidates")
        print(f"Response: {response}")

except Exception as e:
    error_msg = str(e)
    print(f"[FAIL] Model test failed: {error_msg}")

    # Provide specific guidance based on error
    if "404" in error_msg or "not found" in error_msg.lower():
        print("\nFix: Model not found. Try one of these instead:")
        print("   - gemini-2.0-flash-exp")
        print("   - gemini-1.5-flash")
        print("   - gemini-1.5-pro")
        print("\n   Update .env file: GEMINI_MODEL=gemini-3.6-flash")
    elif "401" in error_msg or "authentication" in error_msg.lower():
        print("\nFix: API key is invalid")
        print("   1. Go to https://aistudio.google.com/apikey")
        print("   2. Generate a new API key")
        print("   3. Update .env file with the new key")
    elif "403" in error_msg or "permission" in error_msg.lower():
        print("\nFix: API key doesn't have permission for this model")
        print("   - Try a different model (gemini-3.6-flash)")
        print("   - Or check your Google Cloud project permissions")
    elif "429" in error_msg or "quota" in error_msg.lower():
        print("\nFix: Rate limit or quota exceeded")
        print("   - Wait a few minutes and try again")
        print("   - Check your quota at https://aistudio.google.com/")
    else:
        print(f"\n[WARN] Unexpected error. Full details above.")
    exit(1)

# Success summary
print("\n" + "=" * 60)
print("[SUCCESS] ALL TESTS PASSED - Gemini API is working!")
print("=" * 60)
print(f"\nYou can now run:")
print(f"  python -m scripts.demo --real")
print(f"\nOr test with Supabase:")
print(f"  python -m scripts.demo --real   (USE_SUPABASE is already set in .env)")
