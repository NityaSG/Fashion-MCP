"""
Fashion Trend Analysis MCP Server

Exposes fashion trend data from Instagram via Model Context Protocol.
Allows LLMs to query fashion trends, analyze patterns, and generate insights.
"""

import os
import json
from pathlib import Path
import logging
from typing import Annotated, Literal, Optional, List, Dict, Any
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import Field
import asyncpg

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================


def load_env_file() -> None:
    """
    Lightweight .env loader so creds stay server-side and no CLI env flags are needed.
    Only sets variables that aren't already in the process environment.
    """
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


# Load .env before reading configuration
load_env_file()

DB_CONFIG = {
    "host": os.getenv("SUPABASE_HOST", "localhost"),
    "port": int(os.getenv("SUPABASE_PORT", "5432")),
    "database": os.getenv("SUPABASE_DB", "postgres"),
    "user": os.getenv("SUPABASE_USER", "postgres"),
    "password": os.getenv("SUPABASE_PASSWORD", ""),
}
MEDIA_CDN_BASE_URL = os.getenv(
    "MEDIA_CDN_BASE_URL",
    "https://d99zyv0ifyenn.cloudfront.net",
).rstrip("/")
LEGACY_MEDIA_HOSTS = {
    "ich-next-production.s3.ap-south-1.amazonaws.com",
}

CANONICAL_CATEGORY_ALIASES = {
    "ethnic rtw": "Ethnic RTW",
    "ethnic wear": "Ethnic RTW",
    "ethnicwear": "Ethnic RTW",
    "ethnic": "Ethnic RTW",
    "ethnic ready to wear": "Ethnic RTW",
    "ethnic ready-to-wear": "Ethnic RTW",
    "indian wear": "Ethnic RTW",
    "indian ethnic wear": "Ethnic RTW",
    "western rtw": "Western RTW",
    "western wear": "Western RTW",
    "westernwear": "Western RTW",
    "western": "Western RTW",
    "western ready to wear": "Western RTW",
    "western ready-to-wear": "Western RTW",
    "saree": "Sarees",
    "sarees": "Sarees",
    "streetwear": "Streetwear",
    "street wear": "Streetwear",
    "street style": "Streetwear",
    "sportswear": "Sportswear",
    "sports wear": "Sportswear",
    "sport": "Sportswear",
    "sports": "Sportswear",
    "activewear": "Sportswear",
    "athleisure": "Sportswear",
    "intimates & lounge": "Intimates & Lounge",
    "intimates and lounge": "Intimates & Lounge",
    "intimates": "Intimates & Lounge",
    "loungewear": "Intimates & Lounge",
    "lounge wear": "Intimates & Lounge",
    "loungewear": "Intimates & Lounge",
    "lingerie": "Intimates & Lounge",
    "beauty": "Beauty",
    "home furnishing": "Home Furnishing",
    "home furnishings": "Home Furnishing",
    "home decor": "Home Furnishing",
    "home": "Home Furnishing",
    "other": "Other",
}


# ============================================================================
# Schema Definitions (from your provided schema)
# ============================================================================

TREND_ANALYSIS_SCHEMA = """
CREATE MATERIALIZED VIEW trend_analysis_mv (
  postId integer,
  meta_postId character varying(255),
  insta_shortcode character varying(255),
  permalink character varying(255),
  description text,
  hashtags character varying(255)[],
  media_type character varying(255),
  postDate timestamp with time zone,
  handle character varying(255),
  likes character varying(255),
  numeric_likes double precision,
  category character varying,
  impact double precision,
  trend_score double precision,
  weightage integer,
  brand_id integer,
  brandName character varying,
  brand_handle character varying(255),
  userName character varying(255),
  source character varying,
  genre character varying,
  region character varying(50),
  gender character varying(50),
  age_group character varying(50),
  product character varying(225),
  image_id bigint,
  image_name character varying(255),
  image_link character varying(1000),
  scraping_source_id integer,
  scraping_source character varying(255),
  tac_pantone_name character varying,
  tac_hexcode character varying,
  pantone_code character varying,
  tac_dominance_power integer,
  tac_color_name text,
  tac_rgb_vector vector,
  print_family text,
  print_name text,
  embroidery text,
  wash_type text,
  weave_type text,
  woven_fabric_type text,
  knitted_fabric_type text,
  topwear_gender character varying,
  topwear_shape text,
  topwear_neckline_collar text,
  topwear_sleeve_type text,
  topwear_cuff_type text,
  topwear_hem_type text,
  topwear_length text,
  topwear_pocket_type text,
  topwear_placket_type text,
  topwear_detail_type text,
  bottomwear_shape text,
  bottomwear_hem_type text,
  bottomwear_hem_length text,
  bottomwear_waistband_type text,
  bottomwear_length text,
  bottomwear_pocket_type text,
  bottomwear_detail_type text,
  apparel_name text,
  apparel_type text
);

-- Key Column Descriptions:
-- Category: Ethnic RTW, Western RTW, Sarees, Streetwear, Sportswear, Intimates & Lounge, Beauty, Home Furnishing, Other
-- Genre: Fashion, Food & Travel, Beauty & Grooming, Architecture & Interiors, Art & Culture, Science and Technology, Wedding, Automobile, Politics
-- Region: East India, North India, South India, West India, Global, India, Pan India, Pakistan
-- Gender: Women, Men, Others
-- Age Group: Adult, Youth
-- Product: Apparel, Footwear, Handbags & Bags, Jewellery, Other, Sunglasses & Watches
-- scraping_source_id: 1 or NULL = Instagram, 2 = Website
"""


# ============================================================================
# Application Context for Database Connection
# ============================================================================

@dataclass
class AppContext:
    """Application context holding database pool"""
    db_pool: asyncpg.Pool


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage database connection pool lifecycle"""
    pool = await asyncpg.create_pool(**DB_CONFIG, min_size=2, max_size=10)
    try:
        logger.info("Database connection pool established")
        yield AppContext(db_pool=pool)
    finally:
        await pool.close()
        logger.info("Database connection pool closed")


# ============================================================================
# Initialize FastMCP Server
# ============================================================================

mcp = FastMCP(
    "Fashion Trend Analyzer",
    lifespan=app_lifespan
)


# ============================================================================
# Helper Functions
# ============================================================================

async def execute_query(
    pool: asyncpg.Pool,
    query: str,
    ctx: Context,
    params: Optional[List] = None
) -> List[Dict[str, Any]]:
    """
    Execute a SQL query and return results as list of dictionaries.
    
    Args:
        pool: Database connection pool
        query: SQL query string
        ctx: MCP context for logging
        params: Optional query parameters
    
    Returns:
        List of row dictionaries
    """
    await ctx.debug(f"Executing query: {query[:200]}...")
    
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *(params or []))
            results = [normalize_media_payload(dict(row)) for row in rows]
            await ctx.info(f"Query returned {len(results)} rows")
            return results
        except Exception as e:
            await ctx.error(f"Query execution failed: {str(e)}")
            raise ToolError(f"Database query failed: {str(e)}")


def normalize_whitespace(value: str) -> str:
    """Collapse repeated whitespace in a user-supplied value."""
    return " ".join(value.strip().split())


def sql_literal(value: str) -> str:
    """Escape a string for safe interpolation into a SQL string literal."""
    return value.replace("'", "''")


def normalize_media_url(value: Optional[str]) -> Optional[str]:
    """Rewrite legacy S3 media URLs onto the canonical CDN host."""
    if value is None:
        return None

    text = value.strip()
    if not text or text.startswith("data:"):
        return text

    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return text

    if parsed.netloc not in LEGACY_MEDIA_HOSTS:
        return text

    cdn = urlparse(MEDIA_CDN_BASE_URL)
    return urlunparse(
        (
            cdn.scheme or parsed.scheme,
            cdn.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def normalize_media_payload(value: Any) -> Any:
    """Recursively rewrite legacy media URLs in query results."""
    if isinstance(value, dict):
        return {key: normalize_media_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_media_payload(item) for item in value]
    if isinstance(value, str):
        return normalize_media_url(value)
    return value


def normalize_category(category: Optional[str]) -> Optional[str]:
    """
    Map common natural-language category labels to the canonical database values.

    Examples:
    - "ethnic wear" -> "Ethnic RTW"
    - "western wear" -> "Western RTW"
    - "loungewear" -> "Intimates & Lounge"
    """
    if not category:
        return None

    compact = normalize_whitespace(category)
    lowered = compact.lower()
    if lowered in CANONICAL_CATEGORY_ALIASES:
        return CANONICAL_CATEGORY_ALIASES[lowered]

    if "ethnic" in lowered:
        return "Ethnic RTW"
    if "western" in lowered:
        return "Western RTW"
    if "saree" in lowered:
        return "Sarees"
    if "street" in lowered:
        return "Streetwear"
    if any(token in lowered for token in ("sport", "activewear", "athleisure")):
        return "Sportswear"
    if any(token in lowered for token in ("intimate", "lounge", "lingerie")):
        return "Intimates & Lounge"
    if "beauty" in lowered:
        return "Beauty"
    if "home" in lowered:
        return "Home Furnishing"
    if lowered == "other":
        return "Other"

    return compact


def format_date_filter(
    time_period: Literal["last_week", "last_month", "last_3_months", "last_6_months", "last_year", "all_time"]
) -> str:
    """Generate SQL date filter based on time period"""
    if time_period == "all_time":
        return ""
    
    now = datetime.now()
    periods = {
        "last_week": now - timedelta(days=7),
        "last_month": now - timedelta(days=30),
        "last_3_months": now - timedelta(days=90),
        "last_6_months": now - timedelta(days=180),
        "last_year": now - timedelta(days=365),
    }
    
    start_date = periods[time_period]
    return f'AND "postDate" >= \'{start_date.isoformat()}\''


# ============================================================================
# MCP Resources - Database Schema
# ============================================================================

@mcp.resource("schema://trend_analysis")
async def get_schema() -> str:
    """
    Provides the complete schema of the trend_analysis_mv materialized view.
    Use this to understand available columns and data types when constructing queries.
    """
    return TREND_ANALYSIS_SCHEMA


@mcp.resource("schema://categories")
async def get_categories() -> str:
    """
    Lists all valid values for categorical fields in the database.
    Use this as a reference when filtering data.
    """
    return """
Valid Category Values: Ethnic RTW, Western RTW, Sarees, Streetwear, Sportswear, Intimates & Lounge, Beauty, Home Furnishing, Other

Valid Genre Values: Fashion, Food & Travel, Beauty & Grooming, Architecture & Interiors, Art & Culture, Science and Technology, Wedding, Automobile, Politics

Valid Region Values: East India, North India, South India, West India, Global, India, Pan India, Pakistan

Valid Gender Values: Women, Men, Others

Valid Age Group Values: Adult, Youth

Valid Product Values: Apparel, Footwear, Handbags & Bags, Jewellery, Other, Sunglasses & Watches

Source Types: Celebrity & Influencers (and others)

Scraping Sources:
- scraping_source_id = 1 or NULL: Instagram posts
- scraping_source_id = 2: Website posts
"""


# ============================================================================
# Tool 1: Get Trending Posts
# ============================================================================

@mcp.tool
async def get_trending_posts(
    category: Annotated[
        Optional[str],
        Field(description="Filter by category: Ethnic RTW, Western RTW, Sarees, Streetwear, Sportswear, Intimates & Lounge, Beauty, Home Furnishing, Other")
    ] = None,
    gender: Annotated[
        Optional[Literal["Women", "Men", "Others"]],
        Field(description="Filter by target gender")
    ] = None,
    time_period: Annotated[
        Literal["last_week", "last_month", "last_3_months", "last_6_months", "last_year", "all_time"],
        Field(description="Time period to analyze")
    ] = "last_month",
    limit: Annotated[
        int,
        Field(description="Number of posts to return", ge=1, le=100)
    ] = 20,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Get trending fashion posts ordered by trend_score.
    Returns detailed post information including images, engagement metrics, and fashion attributes.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    category = normalize_category(category)
    
    # Build WHERE clause
    where_conditions = ["1=1"]
    if category:
        where_conditions.append(f"category = '{sql_literal(category)}'")
    if gender:
        where_conditions.append(f"gender = '{gender}'")
    
    date_filter = format_date_filter(time_period)
    if date_filter:
        where_conditions.append(date_filter.replace("AND ", ""))
    
    where_clause = " AND ".join(where_conditions)
    
    query = f"""
    SELECT DISTINCT ON ("meta_postId")
        "postId",
        "meta_postId",
        "insta_shortcode",
        permalink,
        description,
        hashtags,
        "postDate",
        handle,
        "userName",
        "brandName",
        "brand_handle",
        category,
        gender,
        age_group,
        genre,
        region,
        "numeric_likes",
        "trend_score",
        impact,
        "image_link",
        "tac_pantone_name",
        "tac_hexcode",
        apparel_name,
        apparel_type,
        print_name,
        "woven_fabric_type",
        "knitted_fabric_type"
    FROM trend_analysis_mv
    WHERE {where_clause}
    ORDER BY "meta_postId", "trend_score" DESC
    LIMIT {limit}
    """
    
    return await execute_query(pool, query, ctx)


# ============================================================================
# Tool 2: Get Top Brands/Influencers
# ============================================================================

@mcp.tool
async def get_top_brands_or_influencers(
    entity_type: Annotated[
        Literal["brands", "influencers"],
        Field(description="Whether to analyze brands or influencers")
    ] = "brands",
    category: Annotated[
        Optional[str],
        Field(description="Filter by category")
    ] = None,
    time_period: Annotated[
        Literal["last_week", "last_month", "last_3_months", "last_6_months", "last_year", "all_time"],
        Field(description="Time period to analyze")
    ] = "last_month",
    source_filter: Annotated[
        Optional[Literal["instagram", "website"]],
        Field(description="Filter by data source")
    ] = None,
    limit: Annotated[
        int,
        Field(description="Number of results to return", ge=1, le=50)
    ] = 10,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Get top brands or influencers by trend score and post count.
    Includes sample images from their posts.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    category = normalize_category(category)
    
    # Determine grouping field
    if entity_type == "brands":
        group_field = '"brandName"'
        handle_field = '"brand_handle"'
    else:
        group_field = '"userName"'
        handle_field = 'handle'
    
    # Build WHERE clause
    where_conditions = ["1=1"]
    if category:
        where_conditions.append(f"category = '{sql_literal(category)}'")
    
    if source_filter == "instagram":
        where_conditions.append('("scraping_source_id" = 1 OR "scraping_source_id" IS NULL)')
    elif source_filter == "website":
        where_conditions.append('"scraping_source_id" = 2')
    
    date_filter = format_date_filter(time_period)
    if date_filter:
        where_conditions.append(date_filter.replace("AND ", ""))
    
    where_conditions.append(f'{group_field} IS NOT NULL')
    where_conditions.append('"image_link" IS NOT NULL')
    where_conditions.append('permalink IS NOT NULL')
    
    where_clause = " AND ".join(where_conditions)
    
    query = f"""
    WITH unique_posts AS (
        SELECT DISTINCT ON ("meta_postId", {group_field})
            "meta_postId",
            {group_field},
            {handle_field},
            "image_link",
            permalink,
            "postDate",
            "trend_score"
        FROM trend_analysis_mv
        WHERE {where_clause}
        ORDER BY "meta_postId", {group_field}, "postDate" DESC
    ),
    ranked_posts AS (
        SELECT
            "meta_postId",
            {group_field},
            {handle_field},
            "image_link",
            permalink,
            "trend_score",
            ROW_NUMBER() OVER (PARTITION BY {group_field} ORDER BY "postDate" DESC) as rn
        FROM unique_posts
    )
    SELECT
        {group_field} as name,
        {handle_field} as handle,
        COUNT(DISTINCT "meta_postId") AS post_count,
        SUM("trend_score") AS total_trend_score,
        (array_agg("image_link") FILTER (WHERE rn <= 4))[1:4] AS sample_images,
        (array_agg(permalink) FILTER (WHERE rn <= 4))[1:4] AS sample_permalinks
    FROM ranked_posts
    GROUP BY {group_field}, {handle_field}
    ORDER BY total_trend_score DESC
    LIMIT {limit}
    """
    
    return await execute_query(pool, query, ctx)


# ============================================================================
# Tool 3: Get Color Trends
# ============================================================================

@mcp.tool
async def get_color_trends(
    category: Annotated[
        Optional[str],
        Field(description="Filter by category")
    ] = None,
    gender: Annotated[
        Optional[Literal["Women", "Men", "Others"]],
        Field(description="Filter by gender")
    ] = None,
    time_period: Annotated[
        Literal["last_week", "last_month", "last_3_months", "last_6_months", "last_year", "all_time"],
        Field(description="Time period to analyze")
    ] = "last_month",
    limit: Annotated[
        int,
        Field(description="Number of color trends to return", ge=1, le=50)
    ] = 10,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Analyze trending colors in fashion posts.
    Returns top colors by trend score with representative Pantone names and sample images.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    category = normalize_category(category)
    
    # Build WHERE clause
    where_conditions = [
        '"tac_pantone_name" IS NOT NULL',
        '"tac_color_name" IS NOT NULL',
        '"tac_dominance_power" BETWEEN 1 AND 1'
    ]
    
    if category:
        where_conditions.append(f"category = '{sql_literal(category)}'")
    if gender:
        where_conditions.append(f"gender = '{gender}'")
    
    date_filter = format_date_filter(time_period)
    if date_filter:
        where_conditions.append(date_filter.replace("AND ", ""))
    
    where_clause = " AND ".join(where_conditions)
    
    query = f"""
    WITH all_posts_with_scores AS (
        SELECT DISTINCT ON ("postId", "tac_color_name")
            *
        FROM trend_analysis_mv
        WHERE {where_clause}
        ORDER BY "postId", "tac_color_name", "postDate" DESC
    ),
    final_color_families AS (
        SELECT
            "tac_color_name" as color_family_name,
            SUM(trend_score) as color_family_trend_score,
            COUNT(*) as occurrence_count,
            ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM all_posts_with_scores), 2) as color_family_percentage
        FROM all_posts_with_scores
        GROUP BY "tac_color_name"
    ),
    total_counts AS (
        SELECT COUNT(*) as total_count FROM all_posts_with_scores
    ),
    representative_pantones AS (
        SELECT
            "tac_color_name",
            "tac_pantone_name",
            pantone_code as "tac_pantone_code",
            "tac_hexcode",
            COUNT(*) as pantone_count,
            ROW_NUMBER() OVER (PARTITION BY "tac_color_name" ORDER BY COUNT(*) DESC) as rn
        FROM all_posts_with_scores
        WHERE "tac_pantone_name" IS NOT NULL
        GROUP BY "tac_color_name", "tac_pantone_name", pantone_code, "tac_hexcode"
    ),
    trend_rankings AS (
        SELECT
            apws."tac_color_name",
            SUM(apws.trend_score) as total_trend_score,
            SUM(apws.numeric_likes) as total_impact,
            COUNT(*) * 100.0 / MAX(tc.total_count) as contribution,
            COUNT(*) AS post_count,
            MAX(tc.total_count) as total_population_count,
            ROW_NUMBER() OVER (ORDER BY SUM(apws.trend_score) DESC) as trend_rank
        FROM all_posts_with_scores apws
        JOIN final_color_families fcg ON apws."tac_color_name" = fcg.color_family_name
        CROSS JOIN total_counts tc
        GROUP BY apws."tac_color_name"
    ),
    ranked_posts AS (
        SELECT
            "tac_color_name",
            "meta_postId",
            "image_link",
            permalink,
            "postDate",
            trend_score,
            ROW_NUMBER() OVER (PARTITION BY "tac_color_name" ORDER BY "postDate" DESC) as rn
        FROM all_posts_with_scores
        WHERE "image_link" IS NOT NULL AND permalink IS NOT NULL
    )
    SELECT
        tr."tac_color_name" as color_family,
        rp."tac_pantone_name" as pantone_name,
        rp."tac_pantone_code" as pantone_code,
        rp."tac_hexcode" as hex_code,
        tr.trend_rank,
        tr.total_trend_score,
        tr.total_impact,
        ROUND(tr.contribution, 2) as contribution_percent,
        tr.post_count,
        (array_agg(rp_img."image_link") FILTER (WHERE rp_img.rn <= 4))[1:4] AS sample_images,
        (array_agg(rp_img.permalink) FILTER (WHERE rp_img.rn <= 4))[1:4] AS sample_permalinks
    FROM trend_rankings tr
    JOIN representative_pantones rp ON tr."tac_color_name" = rp."tac_color_name" AND rp.rn = 1
    LEFT JOIN ranked_posts rp_img ON tr."tac_color_name" = rp_img."tac_color_name"
    GROUP BY
        tr."tac_color_name",
        rp."tac_pantone_name",
        rp."tac_pantone_code",
        rp."tac_hexcode",
        tr.trend_rank,
        tr.total_trend_score,
        tr.total_impact,
        tr.contribution,
        tr.post_count,
        tr.total_population_count
    ORDER BY tr.trend_rank ASC
    LIMIT {limit}
    """
    
    return await execute_query(pool, query, ctx)


# ============================================================================
# Tool 4: Get Apparel Trends
# ============================================================================

@mcp.tool
async def get_apparel_trends(
    apparel_type_filter: Annotated[
        Optional[str],
        Field(description="Filter by apparel type (e.g., 'Kurta', 'Saree'). Use partial matching.")
    ] = None,
    category: Annotated[
        Optional[str],
        Field(description="Filter by category")
    ] = None,
    gender: Annotated[
        Optional[Literal["Women", "Men", "Others"]],
        Field(description="Filter by gender")
    ] = None,
    time_period: Annotated[
        Literal["last_week", "last_month", "last_3_months", "last_6_months", "last_year", "all_time"],
        Field(description="Time period to analyze")
    ] = "last_month",
    group_by: Annotated[
        Literal["apparel_type", "apparel_name"],
        Field(description="Group by apparel type (broader) or apparel name (specific)")
    ] = "apparel_name",
    limit: Annotated[
        int,
        Field(description="Number of trends to return", ge=1, le=50)
    ] = 10,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Analyze trending apparel types or specific apparel names.
    Returns aggregated metrics with sample images.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    category = normalize_category(category)
    
    # Build WHERE clause
    where_conditions = [f'{group_by} IS NOT NULL']
    
    if apparel_type_filter:
        where_conditions.append(f"apparel_type ILIKE '%{sql_literal(apparel_type_filter)}%'")
    if category:
        where_conditions.append(f"category = '{sql_literal(category)}'")
    if gender:
        where_conditions.append(f"gender = '{gender}'")
    
    date_filter = format_date_filter(time_period)
    if date_filter:
        where_conditions.append(date_filter.replace("AND ", ""))
    
    where_conditions.append('"image_link" IS NOT NULL')
    where_conditions.append('permalink IS NOT NULL')
    
    where_clause = " AND ".join(where_conditions)
    
    query = f"""
    WITH unique_posts AS (
        SELECT DISTINCT ON ("meta_postId", {group_by})
            "meta_postId",
            {group_by},
            "image_link",
            permalink,
            "postDate",
            "trend_score"
        FROM trend_analysis_mv
        WHERE {where_clause}
        ORDER BY "meta_postId", {group_by}, "postDate" DESC
    ),
    ranked_posts AS (
        SELECT
            "meta_postId",
            {group_by},
            "image_link",
            permalink,
            "trend_score",
            ROW_NUMBER() OVER (PARTITION BY {group_by} ORDER BY "postDate" DESC) as rn
        FROM unique_posts
    )
    SELECT
        {group_by} as apparel,
        COUNT(DISTINCT "meta_postId") AS post_count,
        SUM("trend_score") AS total_trend_score,
        (array_agg("image_link") FILTER (WHERE rn <= 4))[1:4] AS sample_images,
        (array_agg(permalink) FILTER (WHERE rn <= 4))[1:4] AS sample_permalinks
    FROM ranked_posts
    GROUP BY {group_by}
    ORDER BY total_trend_score DESC
    LIMIT {limit}
    """
    
    return await execute_query(pool, query, ctx)


# ============================================================================
# Tool 5: Get Print/Pattern Trends
# ============================================================================

@mcp.tool
async def get_print_pattern_trends(
    category: Annotated[
        Optional[str],
        Field(description="Filter by category")
    ] = None,
    gender: Annotated[
        Optional[Literal["Women", "Men", "Others"]],
        Field(description="Filter by gender")
    ] = None,
    time_period: Annotated[
        Literal["last_week", "last_month", "last_3_months", "last_6_months", "last_year", "all_time"],
        Field(description="Time period to analyze")
    ] = "last_month",
    group_by: Annotated[
        Literal["print_family", "print_name"],
        Field(description="Group by print family (broader) or specific print name")
    ] = "print_name",
    limit: Annotated[
        int,
        Field(description="Number of trends to return", ge=1, le=50)
    ] = 10,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Analyze trending prints and patterns in fashion.
    Returns aggregated metrics with sample images.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    category = normalize_category(category)
    
    # Build WHERE clause
    where_conditions = [f'{group_by} IS NOT NULL']
    
    if category:
        where_conditions.append(f"category = '{sql_literal(category)}'")
    if gender:
        where_conditions.append(f"gender = '{gender}'")
    
    date_filter = format_date_filter(time_period)
    if date_filter:
        where_conditions.append(date_filter.replace("AND ", ""))
    
    where_conditions.append('"image_link" IS NOT NULL')
    where_conditions.append('permalink IS NOT NULL')
    
    where_clause = " AND ".join(where_conditions)
    
    query = f"""
    WITH unique_posts AS (
        SELECT DISTINCT ON ("meta_postId", {group_by})
            "meta_postId",
            {group_by},
            "image_link",
            permalink,
            "postDate",
            "trend_score"
        FROM trend_analysis_mv
        WHERE {where_clause}
        ORDER BY "meta_postId", {group_by}, "postDate" DESC
    ),
    ranked_posts AS (
        SELECT
            "meta_postId",
            {group_by},
            "image_link",
            permalink,
            "trend_score",
            ROW_NUMBER() OVER (PARTITION BY {group_by} ORDER BY "postDate" DESC) as rn
        FROM unique_posts
    )
    SELECT
        {group_by} as print_pattern,
        COUNT(DISTINCT "meta_postId") AS post_count,
        SUM("trend_score") AS total_trend_score,
        (array_agg("image_link") FILTER (WHERE rn <= 4))[1:4] AS sample_images,
        (array_agg(permalink) FILTER (WHERE rn <= 4))[1:4] AS sample_permalinks
    FROM ranked_posts
    GROUP BY {group_by}
    ORDER BY total_trend_score DESC
    LIMIT {limit}
    """
    
    return await execute_query(pool, query, ctx)


# ============================================================================
# Tool 6: Get Fabric Trends
# ============================================================================

@mcp.tool
async def get_fabric_trends(
    fabric_type: Annotated[
        Literal["woven", "knitted", "any"],
        Field(description="Type of fabric to analyze")
    ] = "any",
    category: Annotated[
        Optional[str],
        Field(description="Filter by category")
    ] = None,
    gender: Annotated[
        Optional[Literal["Women", "Men", "Others"]],
        Field(description="Filter by gender")
    ] = None,
    time_period: Annotated[
        Literal["last_week", "last_month", "last_3_months", "last_6_months", "last_year", "all_time"],
        Field(description="Time period to analyze")
    ] = "last_month",
    limit: Annotated[
        int,
        Field(description="Number of trends to return", ge=1, le=50)
    ] = 10,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Analyze trending fabric types in fashion.
    Returns aggregated metrics with sample images.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    category = normalize_category(category)
    
    # Determine fabric column
    if fabric_type == "woven":
        fabric_col = '"woven_fabric_type"'
        where_fabric = f'{fabric_col} IS NOT NULL'
    elif fabric_type == "knitted":
        fabric_col = '"knitted_fabric_type"'
        where_fabric = f'{fabric_col} IS NOT NULL'
    else:  # any
        fabric_col = 'COALESCE("woven_fabric_type", "knitted_fabric_type")'
        where_fabric = '("woven_fabric_type" IS NOT NULL OR "knitted_fabric_type" IS NOT NULL)'
    
    # Build WHERE clause
    where_conditions = [where_fabric]
    
    if category:
        where_conditions.append(f"category = '{sql_literal(category)}'")
    if gender:
        where_conditions.append(f"gender = '{gender}'")
    
    date_filter = format_date_filter(time_period)
    if date_filter:
        where_conditions.append(date_filter.replace("AND ", ""))
    
    where_conditions.append('"image_link" IS NOT NULL')
    where_conditions.append('permalink IS NOT NULL')
    
    where_clause = " AND ".join(where_conditions)
    
    # For "any" fabric type, we need to handle both columns in DISTINCT ON
    if fabric_type == "any":
        distinct_cols = '"meta_postId", "woven_fabric_type", "knitted_fabric_type"'
        order_cols = '"meta_postId", "woven_fabric_type", "knitted_fabric_type"'
    else:
        distinct_cols = f'"meta_postId", {fabric_col}'
        order_cols = f'"meta_postId", {fabric_col}'
    
    query = f"""
    WITH unique_posts AS (
        SELECT DISTINCT ON ({distinct_cols})
            "meta_postId",
            {fabric_col} as fabric,
            "image_link",
            permalink,
            "postDate",
            "trend_score"
        FROM trend_analysis_mv
        WHERE {where_clause}
        ORDER BY {order_cols}, "postDate" DESC
    ),
    ranked_posts AS (
        SELECT
            "meta_postId",
            fabric,
            "image_link",
            permalink,
            "trend_score",
            ROW_NUMBER() OVER (PARTITION BY fabric ORDER BY "postDate" DESC) as rn
        FROM unique_posts
        WHERE fabric IS NOT NULL
    )
    SELECT
        fabric as fabric_type,
        COUNT(DISTINCT "meta_postId") AS post_count,
        SUM("trend_score") AS total_trend_score,
        (array_agg("image_link") FILTER (WHERE rn <= 4))[1:4] AS sample_images,
        (array_agg(permalink) FILTER (WHERE rn <= 4))[1:4] AS sample_permalinks
    FROM ranked_posts
    GROUP BY fabric
    ORDER BY total_trend_score DESC
    LIMIT {limit}
    """
    
    return await execute_query(pool, query, ctx)


# ============================================================================
# Tool 7: Execute Custom SQL Query (Open-ended)
# ============================================================================

@mcp.tool
async def execute_custom_sql(
    sql_query: Annotated[
        str,
        Field(description="SQL query to execute. Must be a SELECT query only. Use trend_analysis_mv table.")
    ],
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Execute a custom SQL query against the fashion trends database.
    
    CRITICAL USAGE NOTES:
    - Only SELECT queries are allowed
    - Query the 'trend_analysis_mv' materialized view
    - Use DISTINCT ON ("meta_postId") for unique posts due to view joins
    - Mixed-case columns MUST be double-quoted: "postId", "postDate", "brandName", etc.
    - Lowercase columns like category, gender, apparel_type do NOT need quotes
    - For aggregations, use COUNT(DISTINCT "meta_postId") instead of COUNT(*)
    - Always include sample images with (array_agg("image_link") FILTER (WHERE rn <= 4))[1:4]
    - Refer to schema resource for complete column definitions
    
    This tool allows flexible data exploration and complex analytical queries.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    
    # Security: Only allow SELECT queries
    query_upper = sql_query.strip().upper()
    if not query_upper.startswith("SELECT") and not query_upper.startswith("WITH"):
        raise ToolError(
            "Only SELECT queries are allowed. "
            "Use WITH clauses for CTEs followed by SELECT."
        )
    
    # Block dangerous keywords
    dangerous_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE"]
    for keyword in dangerous_keywords:
        if keyword in query_upper:
            raise ToolError(f"Query contains forbidden keyword: {keyword}")
    
    await ctx.info("Executing custom SQL query")
    await ctx.debug(f"Query: {sql_query}")
    
    return await execute_query(pool, sql_query, ctx)


# ============================================================================
# Tool 8: Get Database Statistics
# ============================================================================

@mcp.tool
async def get_database_statistics(
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Get overall statistics about the fashion trends database.
    Returns counts, date ranges, and distribution summaries.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    
    query = """
    WITH stats AS (
        SELECT
            COUNT(DISTINCT "meta_postId") as total_unique_posts,
            COUNT(DISTINCT "brandName") as total_brands,
            COUNT(DISTINCT "userName") as total_influencers,
            MIN("postDate") as earliest_post,
            MAX("postDate") as latest_post,
            COUNT(DISTINCT category) as category_count,
            COUNT(DISTINCT "tac_pantone_name") as unique_colors,
            COUNT(DISTINCT apparel_type) as unique_apparel_types
        FROM trend_analysis_mv
    ),
    category_dist AS (
        SELECT
            category,
            COUNT(DISTINCT "meta_postId") as post_count
        FROM trend_analysis_mv
        WHERE category IS NOT NULL
        GROUP BY category
        ORDER BY post_count DESC
    ),
    gender_dist AS (
        SELECT
            gender,
            COUNT(DISTINCT "meta_postId") as post_count
        FROM trend_analysis_mv
        WHERE gender IS NOT NULL
        GROUP BY gender
        ORDER BY post_count DESC
    )
    SELECT
        (SELECT row_to_json(stats.*) FROM stats) as overall_stats,
        (SELECT json_agg(row_to_json(category_dist.*)) FROM category_dist) as category_distribution,
        (SELECT json_agg(row_to_json(gender_dist.*)) FROM gender_dist) as gender_distribution
    """
    
    result = await execute_query(pool, query, ctx)
    
    if result and len(result) > 0:
        return result[0]
    return {}


# ============================================================================
# Tool 9: Search Posts by Keywords
# ============================================================================

@mcp.tool
async def search_posts_by_keywords(
    keywords: Annotated[
        str,
        Field(description="Keywords to search in post descriptions and hashtags")
    ],
    category: Annotated[
        Optional[str],
        Field(description="Filter by category")
    ] = None,
    gender: Annotated[
        Optional[Literal["Women", "Men", "Others"]],
        Field(description="Filter by gender")
    ] = None,
    time_period: Annotated[
        Literal["last_week", "last_month", "last_3_months", "last_6_months", "last_year", "all_time"],
        Field(description="Time period to search")
    ] = "last_3_months",
    limit: Annotated[
        int,
        Field(description="Number of posts to return", ge=1, le=100)
    ] = 20,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Search for posts containing specific keywords in descriptions or hashtags.
    Useful for finding posts about specific topics, trends, or events.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    category = normalize_category(category)
    keywords = normalize_whitespace(keywords)
    
    # Build WHERE clause
    where_conditions = [
        f"(description ILIKE '%{sql_literal(keywords)}%' OR array_to_string(hashtags, ' ') ILIKE '%{sql_literal(keywords)}%')"
    ]
    
    if category:
        where_conditions.append(f"category = '{sql_literal(category)}'")
    if gender:
        where_conditions.append(f"gender = '{gender}'")
    
    date_filter = format_date_filter(time_period)
    if date_filter:
        where_conditions.append(date_filter.replace("AND ", ""))
    
    where_clause = " AND ".join(where_conditions)
    
    query = f"""
    SELECT DISTINCT ON ("meta_postId")
        "postId",
        "meta_postId",
        permalink,
        description,
        hashtags,
        "postDate",
        "userName",
        "brandName",
        category,
        gender,
        "trend_score",
        "numeric_likes",
        "image_link"
    FROM trend_analysis_mv
    WHERE {where_clause}
    ORDER BY "meta_postId", "trend_score" DESC
    LIMIT {limit}
    """
    
    return await execute_query(pool, query, ctx)


# ============================================================================
# Tool 10: Compare Time Periods
# ============================================================================

@mcp.tool
async def compare_time_periods(
    metric: Annotated[
        Literal["posts", "colors", "apparel", "brands", "prints"],
        Field(description="What to compare across time periods")
    ],
    category: Annotated[
        Optional[str],
        Field(description="Filter by category")
    ] = None,
    gender: Annotated[
        Optional[Literal["Women", "Men", "Others"]],
        Field(description="Filter by gender")
    ] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Compare trends across different time periods (month-over-month analysis).
    Returns comparative statistics to identify growth or decline in trends.
    """
    pool = ctx.request_context.lifespan_context.db_pool
    category = normalize_category(category)
    
    # Build base WHERE clause
    where_conditions = []
    if category:
        where_conditions.append(f"category = '{sql_literal(category)}'")
    if gender:
        where_conditions.append(f"gender = '{gender}'")
    
    base_where = " AND ".join(where_conditions) if where_conditions else "1=1"
    
    # Define metric-specific queries
    if metric == "posts":
        query = f"""
        WITH monthly_stats AS (
            SELECT
                DATE_TRUNC('month', "postDate") as month,
                COUNT(DISTINCT "meta_postId") as post_count,
                AVG("trend_score") as avg_trend_score,
                SUM("numeric_likes") as total_likes
            FROM trend_analysis_mv
            WHERE {base_where}
                AND "postDate" >= NOW() - INTERVAL '6 months'
            GROUP BY DATE_TRUNC('month', "postDate")
            ORDER BY month DESC
        )
        SELECT
            month,
            post_count,
            ROUND(avg_trend_score::numeric, 2) as avg_trend_score,
            total_likes,
            LAG(post_count) OVER (ORDER BY month) as prev_month_posts,
            ROUND(
                ((post_count::numeric - LAG(post_count) OVER (ORDER BY month)) / 
                NULLIF(LAG(post_count) OVER (ORDER BY month), 0) * 100)::numeric, 
                2
            ) as growth_percent
        FROM monthly_stats
        """
    
    elif metric == "colors":
        query = f"""
        WITH monthly_colors AS (
            SELECT
                DATE_TRUNC('month', "postDate") as month,
                "tac_color_name",
                COUNT(DISTINCT "meta_postId") as post_count
            FROM trend_analysis_mv
            WHERE {base_where}
                AND "postDate" >= NOW() - INTERVAL '3 months'
                AND "tac_color_name" IS NOT NULL
            GROUP BY DATE_TRUNC('month', "postDate"), "tac_color_name"
        ),
        ranked_colors AS (
            SELECT
                month,
                "tac_color_name",
                post_count,
                ROW_NUMBER() OVER (PARTITION BY month ORDER BY post_count DESC) as rank
            FROM monthly_colors
        )
        SELECT
            month,
            "tac_color_name" as color,
            post_count,
            rank
        FROM ranked_colors
        WHERE rank <= 5
        ORDER BY month DESC, rank
        """
    
    elif metric == "apparel":
        query = f"""
        WITH monthly_apparel AS (
            SELECT
                DATE_TRUNC('month', "postDate") as month,
                apparel_name,
                COUNT(DISTINCT "meta_postId") as post_count
            FROM trend_analysis_mv
            WHERE {base_where}
                AND "postDate" >= NOW() - INTERVAL '3 months'
                AND apparel_name IS NOT NULL
            GROUP BY DATE_TRUNC('month', "postDate"), apparel_name
        ),
        ranked_apparel AS (
            SELECT
                month,
                apparel_name,
                post_count,
                ROW_NUMBER() OVER (PARTITION BY month ORDER BY post_count DESC) as rank
            FROM monthly_apparel
        )
        SELECT
            month,
            apparel_name,
            post_count,
            rank
        FROM ranked_apparel
        WHERE rank <= 5
        ORDER BY month DESC, rank
        """
    
    elif metric == "brands":
        query = f"""
        WITH monthly_brands AS (
            SELECT
                DATE_TRUNC('month', "postDate") as month,
                "brandName",
                COUNT(DISTINCT "meta_postId") as post_count,
                SUM("trend_score") as total_trend_score
            FROM trend_analysis_mv
            WHERE {base_where}
                AND "postDate" >= NOW() - INTERVAL '3 months'
                AND "brandName" IS NOT NULL
            GROUP BY DATE_TRUNC('month', "postDate"), "brandName"
        ),
        ranked_brands AS (
            SELECT
                month,
                "brandName",
                post_count,
                total_trend_score,
                ROW_NUMBER() OVER (PARTITION BY month ORDER BY total_trend_score DESC) as rank
            FROM monthly_brands
        )
        SELECT
            month,
            "brandName" as brand,
            post_count,
            ROUND(total_trend_score::numeric, 2) as total_trend_score,
            rank
        FROM ranked_brands
        WHERE rank <= 5
        ORDER BY month DESC, rank
        """
    
    else:  # prints
        query = f"""
        WITH monthly_prints AS (
            SELECT
                DATE_TRUNC('month', "postDate") as month,
                print_name,
                COUNT(DISTINCT "meta_postId") as post_count
            FROM trend_analysis_mv
            WHERE {base_where}
                AND "postDate" >= NOW() - INTERVAL '3 months'
                AND print_name IS NOT NULL
            GROUP BY DATE_TRUNC('month', "postDate"), print_name
        ),
        ranked_prints AS (
            SELECT
                month,
                print_name,
                post_count,
                ROW_NUMBER() OVER (PARTITION BY month ORDER BY post_count DESC) as rank
            FROM monthly_prints
        )
        SELECT
            month,
            print_name,
            post_count,
            rank
        FROM ranked_prints
        WHERE rank <= 5
        ORDER BY month DESC, rank
        """
    
    results = await execute_query(pool, query, ctx)
    
    return {
        "metric": metric,
        "category": category,
        "gender": gender,
        "comparison_data": results
    }


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "http").strip().lower()

    if transport in {"http", "streamable-http", "sse"}:
        host = os.getenv("MCP_HOST", os.getenv("FASTMCP_HOST", "127.0.0.1"))
        port = int(os.getenv("MCP_PORT", os.getenv("FASTMCP_PORT", "8000")))
        mcp.run(transport=transport, host=host, port=port)
    else:
        # Default to stdio for desktop MCP clients and local testing.
        mcp.run()
