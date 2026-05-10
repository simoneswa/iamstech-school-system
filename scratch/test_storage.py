import sys
import os
# Add the project root to sys.path to allow importing from lib
sys.path.append(os.getcwd())

try:
    from lib.storage import upload_to_bucket
    print("SUCCESS: Successfully imported upload_to_bucket from lib.storage")
    
    # Test upload with fake data if env vars are present
    if os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_KEY'):
        print("Testing cloud upload...")
        test_data = b"test content"
        url = upload_to_bucket(test_data, "test_file.txt", "text/plain", "tests")
        if url:
            print(f"SUCCESS: Uploaded to cloud. URL: {url}")
        else:
            print("FAILURE: Cloud upload returned None")
    else:
        print("INFO: Skipping cloud upload test (missing environment variables)")

except Exception as e:
    print(f"FAILURE: {e}")
    import traceback
    traceback.print_exc()
