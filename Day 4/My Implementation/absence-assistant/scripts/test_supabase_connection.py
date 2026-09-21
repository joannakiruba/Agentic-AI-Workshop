"""Test Supabase connection with the provided credentials."""
import os
import sys

# Test 1: Check if credentials are available
print("=" * 60)
print("SUPABASE CONNECTION TEST")
print("=" * 60)

SUPABASE_URL = "https://vgnflbiwlqgkkaodkbkj.supabase.co"
SUPABASE_KEY = "sb_publishable_91vY7O_D86Zb4oiEv9aMSg_RSgtwKCI"

print(f"\n✅ Supabase URL: {SUPABASE_URL}")
print(f"✅ Using publishable key: {SUPABASE_KEY[:20]}...")

# Test 2: Check if supabase library is installed
print("\n" + "-" * 60)
print("Test 1: Checking dependencies...")
print("-" * 60)

try:
    from supabase import create_client
    print("✅ supabase-py library installed")
except ImportError:
    print("❌ supabase-py library NOT installed")
    print("\n🔧 Fix: Run this command:")
    print("   pip install supabase")
    sys.exit(1)

# Test 3: Create client
print("\n" + "-" * 60)
print("Test 2: Creating Supabase client...")
print("-" * 60)

try:
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase client created successfully")
except Exception as e:
    print(f"❌ Failed to create client: {e}")
    sys.exit(1)

# Test 4: Check if tables exist
print("\n" + "-" * 60)
print("Test 3: Checking if database tables exist...")
print("-" * 60)

tables_to_check = ["employee", "holiday", "policy", "leave_request", "notification"]
tables_exist = {}

for table in tables_to_check:
    try:
        response = client.table(table).select("*").limit(1).execute()
        tables_exist[table] = True
        count = len(response.data) if response.data else 0
        print(f"✅ {table:<20} exists (found {count} rows)")
    except Exception as e:
        tables_exist[table] = False
        print(f"❌ {table:<20} NOT FOUND or no access")
        print(f"   Error: {str(e)[:80]}")

# Test 5: Try to read employee data
if tables_exist.get("employee"):
    print("\n" + "-" * 60)
    print("Test 4: Reading employee data...")
    print("-" * 60)

    try:
        response = client.table("employee").select("employee_id, name, dept").execute()
        if response.data:
            print(f"✅ Successfully read {len(response.data)} employees:")
            for emp in response.data:
                print(f"   - {emp['employee_id']}: {emp['name']} ({emp['dept']})")
        else:
            print("⚠️  No employee data found (table is empty)")
    except Exception as e:
        print(f"❌ Failed to read employee data: {e}")

# Test 6: Test the SupabaseLeaveDb class
print("\n" + "-" * 60)
print("Test 5: Testing SupabaseLeaveDb class...")
print("-" * 60)

try:
    from app.supabase_client import SupabaseLeaveDb

    db = SupabaseLeaveDb(SUPABASE_URL, SUPABASE_KEY)
    print("✅ SupabaseLeaveDb initialized")

    # Test get_employee
    try:
        emp = db.get_employee("E001")
        if emp:
            print(f"✅ get_employee('E001'): {emp['name']}")
        else:
            print("⚠️  Employee E001 not found (needs seed data)")
    except Exception as e:
        print(f"❌ get_employee failed: {e}")

    # Test get_leave_balance
    try:
        balance = db.get_leave_balance("E001")
        if balance:
            print(f"✅ get_leave_balance('E001'): {balance['annual_leave']} annual, "
                  f"{balance['sick_leave']} sick, {balance['casual_leave']} casual")
        else:
            print("⚠️  Balance not found for E001")
    except Exception as e:
        print(f"❌ get_leave_balance failed: {e}")

    # Test list_holidays
    try:
        holidays = db.list_holidays()
        print(f"✅ list_holidays(): Found {len(holidays)} holidays")
        if holidays:
            print(f"   Example: {holidays[0]['date']} - {holidays[0]['name']}")
    except Exception as e:
        print(f"❌ list_holidays failed: {e}")

except ImportError as e:
    print(f"❌ Failed to import SupabaseLeaveDb: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

all_tables_exist = all(tables_exist.values())

if all_tables_exist:
    print("✅ All tables exist - Database is ready!")
    print("\n📝 Next steps:")
    print("   1. Run the seed data SQL (see SUPABASE_SETUP.md)")
    print("   2. Update .env file with these credentials")
    print("   3. Run: python -m scripts.demo (to test with scripted models)")
else:
    print("❌ Some tables are missing")
    print("\n🔧 Next steps:")
    print("   1. Go to Supabase Dashboard > SQL Editor")
    print("   2. Copy the schema from SUPABASE_SETUP.md")
    print("   3. Run the schema SQL to create tables")
    print("   4. Run this test again")
    print("\nMissing tables:")
    for table, exists in tables_exist.items():
        if not exists:
            print(f"   - {table}")

print("\n" + "=" * 60)
