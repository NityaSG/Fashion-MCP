"""
Test script for Fashion Trends MCP Server

Run this to verify your database connection and server setup.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[1]


async def test_connection():
    """Test database connection and basic queries"""
    
    # Load environment variables
    load_dotenv(REPO_ROOT / ".env")
    
    print("🔍 Testing Fashion Trends MCP Server Setup\n")
    print("=" * 60)
    
    # Check environment variables
    print("\n1. Checking Environment Variables...")
    required_vars = ["SUPABASE_HOST", "SUPABASE_DB", "SUPABASE_USER", "SUPABASE_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"   ❌ Missing environment variables: {', '.join(missing_vars)}")
        print("   💡 Create a .env file with your Supabase credentials")
        return False
    
    print("   ✅ All environment variables present")
    
    # Test database connection
    print("\n2. Testing Database Connection...")
    try:
        conn = await asyncpg.connect(
            host=os.getenv("SUPABASE_HOST"),
            port=int(os.getenv("SUPABASE_PORT", "5432")),
            database=os.getenv("SUPABASE_DB"),
            user=os.getenv("SUPABASE_USER"),
            password=os.getenv("SUPABASE_PASSWORD"),
        )
        print("   ✅ Database connection successful")
        
        # Test table exists
        print("\n3. Checking trend_analysis_mv Table...")
        result = await conn.fetchval("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_name = 'trend_analysis_mv'
        """)
        
        if result == 0:
            print("   ❌ Table 'trend_analysis_mv' not found")
            print("   💡 Ensure the materialized view exists in your database")
            await conn.close()
            return False
        
        print("   ✅ trend_analysis_mv table found")
        
        # Get table statistics
        print("\n4. Getting Database Statistics...")
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(DISTINCT "meta_postId") as unique_posts,
                MIN("postDate") as earliest_post,
                MAX("postDate") as latest_post
            FROM trend_analysis_mv
        """)
        
        print(f"   📊 Total rows: {stats['total_rows']:,}")
        print(f"   📊 Unique posts: {stats['unique_posts']:,}")
        print(f"   📊 Date range: {stats['earliest_post']} to {stats['latest_post']}")
        
        # Test sample query
        print("\n5. Testing Sample Query...")
        sample = await conn.fetchrow("""
            SELECT DISTINCT ON ("meta_postId")
                "meta_postId",
                "brandName",
                category,
                gender,
                "trend_score"
            FROM trend_analysis_mv
            WHERE "brandName" IS NOT NULL
            ORDER BY "meta_postId", "trend_score" DESC
            LIMIT 1
        """)
        
        if sample:
            print(f"   ✅ Sample query successful")
            print(f"   📝 Sample post: {sample['meta_postId']}")
            print(f"   📝 Brand: {sample['brandName']}")
            print(f"   📝 Category: {sample['category']}")
            print(f"   📝 Trend Score: {sample['trend_score']}")
        
        await conn.close()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("\n🚀 Your server is ready to use!")
        print("\nNext steps:")
        print("1. Run: fastmcp dev fashion_trends_mcp_server.py")
        print("2. Or install in Claude Desktop (see docs/backend-server.md)")
        print("=" * 60)
        
        return True
        
    except asyncpg.InvalidPasswordError:
        print("   ❌ Authentication failed - check your password")
        return False
    except asyncpg.InvalidCatalogNameError:
        print("   ❌ Database not found - check your database name")
        return False
    except Exception as e:
        print(f"   ❌ Connection failed: {str(e)}")
        return False


async def test_fastmcp_import():
    """Test that FastMCP is properly installed"""
    print("\n0. Checking FastMCP Installation...")
    try:
        import fastmcp
        print(f"   ✅ FastMCP version {fastmcp.__version__} installed")
        return True
    except ImportError:
        print("   ❌ FastMCP not installed")
        print("   💡 Run: pip install fastmcp asyncpg")
        return False


if __name__ == "__main__":
    async def main():
        # Test imports first
        if not await test_fastmcp_import():
            return
        
        # Test connection
        await test_connection()
    
    # Run tests
    asyncio.run(main())
