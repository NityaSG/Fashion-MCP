# Fashion Trends MCP Server

Model Context Protocol server exposing fashion trend analysis data from Instagram. Enables LLMs to query, analyze, and generate insights from thousands of daily fashion posts.

## 🎯 What This Enables

Your LLM can now:
- **Discover Trends**: "What are the top 5 trending colors in women's ethnic wear this month?"
- **Analyze Patterns**: "Compare saree trends between North India and South India"
- **Track Influencers**: "Which Instagram influencer posted the most about kurtas in August?"
- **Sequential Discovery**: Ask follow-up questions that build on previous queries
- **Visual Analysis**: Get sample images with every trend analysis
- **Custom Queries**: Execute any SQL query for deep data exploration

The LLM will automatically make multiple sequential tool calls to explore your data, create visualizations using Python, and generate comprehensive reports.

## 📋 Prerequisites

- Python 3.10 or higher
- Supabase PostgreSQL database with `trend_analysis_mv` materialized view
- Claude Desktop or any MCP-compatible client

## 🚀 Quick Start

### 1. Installation

```bash
# Clone or download the server file
cd /path/to/server

# Install dependencies
pip install -r requirements.txt

# Or install directly
pip install fastmcp asyncpg
```

### 2. Configuration

Create a `.env` file with your Supabase credentials:

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

Your `.env` should contain:
```
SUPABASE_HOST=your-project.supabase.co
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=your-password-here
```

### 3. Test the Server

```bash
# Test with FastMCP dev mode
fastmcp dev fashion_trends_mcp_server.py

# Or use MCP Inspector
npx @modelcontextprotocol/inspector python fashion_trends_mcp_server.py
```

## 🖥️ Claude Desktop Integration

### Automatic Installation (Recommended)

```bash
fastmcp install claude-desktop fashion_trends_mcp_server.py \
  --server-name "fashion-trends" \
  --with asyncpg \
  --env SUPABASE_HOST=your-project.supabase.co \
  --env SUPABASE_PORT=5432 \
  --env SUPABASE_DB=postgres \
  --env SUPABASE_USER=postgres \
  --env SUPABASE_PASSWORD=your-password
```

### Manual Installation

Edit your Claude Desktop config file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add this configuration:

```json
{
  "mcpServers": {
    "fashion-trends": {
      "command": "uv",
      "args": [
        "run",
        "--with", "fastmcp",
        "--with", "asyncpg",
        "fastmcp", "run",
        "/absolute/path/to/fashion_trends_mcp_server.py"
      ],
      "env": {
        "SUPABASE_HOST": "your-project.supabase.co",
        "SUPABASE_PORT": "5432",
        "SUPABASE_DB": "postgres",
        "SUPABASE_USER": "postgres",
        "SUPABASE_PASSWORD": "your-password"
      }
    }
  }
}
```

**Important**: 
- Use absolute paths (e.g., `/Users/yourname/projects/mcp/fashion_trends_mcp_server.py`)
- Restart Claude Desktop completely after configuration
- Look for the 🔨 hammer icon to confirm the server loaded

### Debugging

Check logs if the server doesn't appear:
- **macOS**: `~/Library/Logs/Claude/mcp*.log`
- **Windows**: `%APPDATA%\Claude\Logs\`

## 🛠️ Available Tools

### 1. `get_trending_posts`
Get trending fashion posts with filters.

**Example prompts:**
- "Show me the top 20 trending posts in Ethnic RTW for women this month"
- "What are the most popular sarees from last week?"

### 2. `get_top_brands_or_influencers`
Analyze top brands or influencers by trend score.

**Example prompts:**
- "Who are the top 10 fashion influencers posting about Western RTW?"
- "Which brands had the most trending posts on Instagram last month?"
- "Top 5 brands in men's streetwear from websites only"

### 3. `get_color_trends`
Deep color trend analysis with Pantone names and hex codes.

**Example prompts:**
- "What are the top 5 trending colors in women's ethnic wear?"
- "Show me color trends for sarees in the last 3 months"
- "Trending colors in youth fashion this year"

### 4. `get_apparel_trends`
Analyze trending apparel types and specific garment names.

**Example prompts:**
- "What kurta styles are trending in North India?"
- "Top 10 apparel trends in Western RTW for women"
- "Trending apparel under sarees category"

### 5. `get_print_pattern_trends`
Discover trending prints and patterns.

**Example prompts:**
- "What print patterns are popular in ethnic wear?"
- "Top 5 trending print families this month"
- "Show me floral pattern trends for women"

### 6. `get_fabric_trends`
Analyze fabric type trends (woven, knitted, or both).

**Example prompts:**
- "What woven fabrics are trending in sarees?"
- "Top fabric trends in women's clothing"
- "Trending knitted fabrics in streetwear"

### 7. `execute_custom_sql`
Execute any custom SQL query for advanced analysis.

**Example prompts:**
- "Execute SQL to find posts with both floral prints and blue colors"
- "Query the database for posts from influencers with over 100K likes"
- "Find correlation between sleeve types and trend scores"

**Safety**: Only SELECT queries allowed. Destructive operations are blocked.

### 8. `get_database_statistics`
Get overall database statistics and distributions.

**Example prompt:**
- "Give me an overview of the fashion trends database"

### 9. `search_posts_by_keywords`
Search posts by keywords in descriptions and hashtags.

**Example prompts:**
- "Find posts about wedding fashion in the last month"
- "Search for posts mentioning 'sustainable' or 'eco-friendly'"

### 10. `compare_time_periods`
Month-over-month trend comparison analysis.

**Example prompts:**
- "Compare color trends across the last 3 months"
- "Show me brand performance month-over-month"
- "How have apparel trends changed in the last quarter?"

## 📚 Resources

The server exposes two resources for schema information:

### `schema://trend_analysis`
Complete database schema with column descriptions.

### `schema://categories`
Valid values for all categorical fields (categories, genres, regions, etc.).

## 💡 Usage Examples

### Example 1: Sequential Discovery

```
User: "What are the top trending colors in women's ethnic wear?"

Claude: [calls get_color_trends]
"The top 5 colors are Light Gray, Beige, Black, White, and Pink..."

User: "Show me which influencers are posting these colors"

Claude: [calls execute_custom_sql with color filter]
"Here are the top influencers posting about Light Gray..."

User: "Create a chart comparing these influencers' engagement"

Claude: [uses built-in Python to create matplotlib chart]
```

### Example 2: Comprehensive Analysis

```
User: "I want a complete analysis of saree trends in South India for August"

Claude will automatically:
1. Call get_trending_posts to get saree data
2. Call get_color_trends for color analysis
3. Call get_print_pattern_trends for pattern insights
4. Call get_top_brands_or_influencers for key players
5. Use Python to create visualizations
6. Generate a comprehensive markdown report with images
```

### Example 3: Custom Deep Dive

```
User: "Find posts where Light Gray colors appear with embroidered details"

Claude: [calls execute_custom_sql]
WITH filtered_posts AS (
  SELECT DISTINCT ON ("meta_postId") ...
  WHERE "tac_color_name" ILIKE '%gray%'
    AND ("topwear_detail_type" ILIKE '%embroid%' 
         OR "bottomwear_detail_type" ILIKE '%embroid%')
)
SELECT ...
```

## 🔍 Query Best Practices

The server automatically handles:
- **Deduplication**: Uses `DISTINCT ON ("meta_postId")` for unique posts
- **Mixed-case columns**: Auto-quotes columns like `"postDate"`, `"brandName"`
- **Image aggregation**: Includes 3-4 sample images per trend
- **Most recent first**: Orders by `"postDate" DESC` for freshness

Your LLM receives these benefits automatically when using any tool.

## 🔐 Security Notes

- **SQL Injection**: This is an internal testing server. The `execute_custom_sql` tool blocks destructive operations (DROP, DELETE, UPDATE, etc.) but relies on read-only database credentials for full protection.
- **Production Use**: For production, implement:
  - Parameterized queries
  - Query timeout limits
  - Result size limits
  - User authentication
  - Audit logging

## 📊 Database Schema Overview

The `trend_analysis_mv` materialized view contains:

**Post Identification**: postId, meta_postId, permalink, insta_shortcode
**Content**: description, hashtags, media_type
**Metadata**: postDate, likes, numeric_likes, trend_score, impact
**Brand/User**: brandName, userName, handle, brand_handle
**Classification**: category, gender, age_group, genre, region, product
**Images**: image_id, image_name, image_link
**Colors**: tac_pantone_name, tac_hexcode, tac_color_name, pantone_code
**Prints**: print_family, print_name
**Fabrics**: woven_fabric_type, knitted_fabric_type, wash_type, weave_type
**Apparel Details**: apparel_name, apparel_type
**Topwear**: topwear_shape, topwear_neckline_collar, topwear_sleeve_type, etc.
**Bottomwear**: bottomwear_shape, bottomwear_hem_type, bottomwear_length, etc.

See `schema://trend_analysis` resource for complete details.

## 🚢 HTTP Deployment

To run as an HTTP server (for web apps or multiple clients):

```python
# In fashion_trends_mcp_server.py, change the last line to:
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
```

Or via CLI:
```bash
fastmcp run fashion_trends_mcp_server.py --transport http --port 8000
```

## 🤝 Contributing

This is an internal testing project. Extend the server by:

1. **Adding Tools**: Use `@mcp.tool` decorator for new predefined queries
2. **Adding Resources**: Use `@mcp.resource()` for static reference data
3. **Enhancing Queries**: Modify CTEs in tools for more sophisticated analysis

Example - Add a new tool:

```python
@mcp.tool
async def get_seasonal_trends(
    season: Literal["spring", "summer", "fall", "winter"],
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """Analyze fashion trends by season."""
    # Your implementation here
    pass
```

## 📝 License

Internal testing project for fashion forecasting company.

## 🆘 Support

For issues:
1. Check Claude Desktop logs
2. Test with `fastmcp dev fashion_trends_mcp_server.py`
3. Verify database connectivity: `psql -h $SUPABASE_HOST -U $SUPABASE_USER -d $SUPABASE_DB`
4. Ensure Python 3.10+: `python --version`

## 🎉 What's Next?

Once integrated with Claude or ChatGPT:
- Ask questions in natural language
- Let the LLM discover data through sequential queries
- Generate charts, reports, and visualizations
- Export findings to documents
- Build automated trend reports

Your fashion data is now conversational! 🚀
