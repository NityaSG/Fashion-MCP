"""
Example Usage Script for Fashion Trends MCP Server

This demonstrates how to interact with the MCP server programmatically
for testing and development purposes.
"""

import asyncio
import sys
from pathlib import Path

from fastmcp import Client

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fashion_trends_mcp_server import mcp


async def example_queries():
    """Run example queries against the MCP server"""
    
    print("🎨 Fashion Trends MCP Server - Example Queries\n")
    print("=" * 70)
    
    # Create in-memory client
    async with Client(mcp) as client:
        
        # Example 1: Get trending posts
        print("\n1️⃣ Getting Trending Posts in Women's Ethnic RTW...\n")
        result = await client.call_tool(
            "get_trending_posts",
            {
                "category": "Ethnic RTW",
                "gender": "Women",
                "time_period": "last_month",
                "limit": 5
            }
        )
        
        posts = result.content[0].text
        print(f"Found {len(eval(posts))} trending posts")
        print(f"Sample: {eval(posts)[0] if posts != '[]' else 'No posts found'}\n")
        
        # Example 2: Get color trends
        print("\n2️⃣ Analyzing Color Trends...\n")
        result = await client.call_tool(
            "get_color_trends",
            {
                "category": "Ethnic RTW",
                "gender": "Women",
                "time_period": "last_month",
                "limit": 5
            }
        )
        
        colors = eval(result.content[0].text)
        print(f"Top 5 Trending Colors:")
        for i, color in enumerate(colors[:5], 1):
            print(f"  {i}. {color.get('pantone_name', 'N/A')} "
                  f"({color.get('hex_code', 'N/A')}) - "
                  f"{color.get('post_count', 0)} posts")
        
        # Example 3: Get top influencers
        print("\n3️⃣ Finding Top Instagram Influencers...\n")
        result = await client.call_tool(
            "get_top_brands_or_influencers",
            {
                "entity_type": "influencers",
                "category": "Ethnic RTW",
                "source_filter": "instagram",
                "time_period": "last_month",
                "limit": 5
            }
        )
        
        influencers = eval(result.content[0].text)
        print(f"Top 5 Influencers:")
        for i, inf in enumerate(influencers[:5], 1):
            print(f"  {i}. {inf.get('name', 'N/A')} (@{inf.get('handle', 'N/A')}) - "
                  f"{inf.get('post_count', 0)} posts, "
                  f"trend score: {inf.get('total_trend_score', 0):.2f}")
        
        # Example 4: Get apparel trends
        print("\n4️⃣ Analyzing Apparel Trends (Kurtas)...\n")
        result = await client.call_tool(
            "get_apparel_trends",
            {
                "apparel_type_filter": "kurta",
                "category": "Ethnic RTW",
                "gender": "Women",
                "time_period": "last_month",
                "group_by": "apparel_name",
                "limit": 5
            }
        )
        
        apparels = eval(result.content[0].text)
        print(f"Top 5 Kurta Styles:")
        for i, app in enumerate(apparels[:5], 1):
            print(f"  {i}. {app.get('apparel', 'N/A')} - "
                  f"{app.get('post_count', 0)} posts")
        
        # Example 5: Custom SQL query
        print("\n5️⃣ Running Custom SQL Query...\n")
        custom_query = """
        SELECT 
            category,
            COUNT(DISTINCT "meta_postId") as post_count,
            AVG("trend_score") as avg_trend_score
        FROM trend_analysis_mv
        WHERE "postDate" >= NOW() - INTERVAL '1 month'
        GROUP BY category
        ORDER BY post_count DESC
        LIMIT 5
        """
        
        result = await client.call_tool(
            "execute_custom_sql",
            {"sql_query": custom_query}
        )
        
        categories = eval(result.content[0].text)
        print(f"Top 5 Categories by Post Count:")
        for i, cat in enumerate(categories[:5], 1):
            print(f"  {i}. {cat.get('category', 'N/A')} - "
                  f"{cat.get('post_count', 0)} posts, "
                  f"avg trend score: {cat.get('avg_trend_score', 0):.2f}")
        
        # Example 6: Database statistics
        print("\n6️⃣ Getting Database Overview...\n")
        result = await client.call_tool("get_database_statistics", {})
        
        stats = eval(result.content[0].text)
        overall = stats.get('overall_stats', {})
        print(f"Database Statistics:")
        print(f"  Total unique posts: {overall.get('total_unique_posts', 0):,}")
        print(f"  Total brands: {overall.get('total_brands', 0):,}")
        print(f"  Total influencers: {overall.get('total_influencers', 0):,}")
        print(f"  Unique colors: {overall.get('unique_colors', 0):,}")
        print(f"  Date range: {overall.get('earliest_post', 'N/A')} to "
              f"{overall.get('latest_post', 'N/A')}")
        
        # Example 7: Search by keywords
        print("\n7️⃣ Searching Posts by Keywords...\n")
        result = await client.call_tool(
            "search_posts_by_keywords",
            {
                "keywords": "wedding",
                "category": "Ethnic RTW",
                "time_period": "last_month",
                "limit": 3
            }
        )
        
        search_results = eval(result.content[0].text)
        print(f"Found {len(search_results)} posts about 'wedding'")
        if search_results:
            print(f"Sample: {search_results[0].get('description', 'N/A')[:100]}...")
        
        print("\n" + "=" * 70)
        print("✅ All example queries completed successfully!")
        print("\n💡 These same queries can be triggered by natural language")
        print("   prompts in Claude Desktop or ChatGPT when the MCP server")
        print("   is configured.")
        print("=" * 70)


async def test_resources():
    """Test accessing MCP resources"""
    
    print("\n📚 Testing MCP Resources\n")
    print("=" * 70)
    
    async with Client(mcp) as client:
        # Get schema resource
        print("\n1️⃣ Getting Database Schema...")
        result = await client.read_resource("schema://trend_analysis")
        schema = result.content[0].text
        print(f"   ✅ Schema retrieved ({len(schema)} characters)")
        print(f"   Preview: {schema[:200]}...")
        
        # Get categories resource
        print("\n2️⃣ Getting Valid Categories...")
        result = await client.read_resource("schema://categories")
        categories = result.content[0].text
        print(f"   ✅ Categories retrieved")
        print(f"   {categories[:300]}...")
        
        print("\n" + "=" * 70)


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  Fashion Trends MCP Server - Programmatic Testing")
    print("=" * 70)
    
    async def main():
        try:
            # Run example queries
            await example_queries()
            
            # Test resources
            await test_resources()
            
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            print("\n💡 Make sure:")
            print("   1. Your .env file is configured")
            print("   2. Database connection is working (run python scripts/test_connection.py)")
            print("   3. FastMCP and asyncpg are installed")
    
    asyncio.run(main())
