/**
 * Fashion Trends MCP Apps bridge for ChatGPT.
 *
 * This server exposes UI-enabled MCP tools and proxies tool execution to the
 * existing Python FastMCP server over Streamable HTTP.
 *
 * Backend default:
 *   http://127.0.0.1:8000/mcp
 */

import { createServer } from "node:http";
import {
  createReadStream,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
} from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";

const INITIAL_ENV_KEYS = new Set(Object.keys(process.env));

function loadLocalEnv(envFileUrl, { override = false } = {}) {
  const envPath = fileURLToPath(envFileUrl);
  if (!existsSync(envPath)) {
    return;
  }

  const envFile = readFileSync(envPath, "utf8");
  for (const rawLine of envFile.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const cleanedLine = line.startsWith("export ") ? line.slice(7) : line;
    const separatorIndex = cleanedLine.indexOf("=");
    if (separatorIndex <= 0) {
      continue;
    }

    const key = cleanedLine.slice(0, separatorIndex).trim();
    if (!key) {
      continue;
    }

    if (INITIAL_ENV_KEYS.has(key)) {
      continue;
    }

    if (!override && process.env[key] !== undefined) {
      continue;
    }

    let value = cleanedLine.slice(separatorIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    process.env[key] = value.replace(/\\n/g, "\n");
  }
}

loadLocalEnv(new URL(".env.example", import.meta.url));
loadLocalEnv(new URL(".env", import.meta.url), { override: true });

const PORT = Number(process.env.PORT ?? 8787);
const LEGACY_API_URL = (process.env.API_URL ?? "").trim();
const BACKEND_MCP_URL = normalizeBackendMcpUrl(
  process.env.BACKEND_MCP_URL ?? LEGACY_API_URL ?? "http://127.0.0.1:8000/mcp"
);
const MEDIA_CDN_BASE_URL = normalizeBaseUrl(
  process.env.MEDIA_CDN_BASE_URL ?? "https://d99zyv0ifyenn.cloudfront.net"
);
const CONFIGURED_PUBLIC_BASE_URL = (process.env.PUBLIC_BASE_URL ?? "").replace(
  /\/$/,
  ""
);
const PUBLIC_BASE_URL = CONFIGURED_PUBLIC_BASE_URL || `http://localhost:${PORT}`;
const PUBLIC_BASE_ORIGIN = new URL(PUBLIC_BASE_URL).origin;
const MEDIA_CDN_ORIGIN = new URL(MEDIA_CDN_BASE_URL).origin;
const STATIC_DIR = fileURLToPath(new URL("static", import.meta.url));
const STATIC_IMAGE_DIR = join(STATIC_DIR, "image");
const MCP_PATH = "/mcp";
const WIDGET_URI = "ui://widget/app.v2.html";
const LEGACY_MEDIA_HOSTS = new Set([
  "ich-next-production.s3.ap-south-1.amazonaws.com",
]);

mkdirSync(STATIC_IMAGE_DIR, { recursive: true });

const widgetHtml = readFileSync(
  new URL("widget/app.html", import.meta.url),
  "utf8"
);
const testHarnessHtml = readFileSync(
  new URL("test-harness.html", import.meta.url),
  "utf8"
);

const PERIOD_LABELS = {
  last_week: "Last week",
  last_month: "Last month",
  last_3_months: "Last 3 months",
  last_6_months: "Last 6 months",
  last_year: "Last year",
  all_time: "All time",
};

const widgetDomains = [...new Set([PUBLIC_BASE_URL, MEDIA_CDN_ORIGIN])];

const widgetResourceMeta = {
  ui: {
    prefersBorder: true,
    csp: {
      connectDomains: widgetDomains,
      resourceDomains: widgetDomains,
    },
  },
};

const widgetMeta = {
  ui: { resourceUri: WIDGET_URI },
  "openai/outputTemplate": WIDGET_URI,
  "openai/widgetCSP": {
    connect_domains: widgetDomains,
    resource_domains: widgetDomains,
  },
};

const timePeriodEnum = z.enum([
  "last_week",
  "last_month",
  "last_3_months",
  "last_6_months",
  "last_year",
  "all_time",
]);
const genderEnum = z.enum(["Women", "Men", "Others"]);
const entityTypeEnum = z.enum(["brands", "influencers"]);
const sourceFilterEnum = z.enum(["instagram", "website"]);

function normalizeBackendMcpUrl(rawValue) {
  const candidate = (rawValue ?? "").trim();
  const url = new URL(candidate);

  if (!url.pathname || url.pathname === "/") {
    url.pathname = "/mcp";
  } else if (!url.pathname.endsWith("/mcp")) {
    url.pathname = `${url.pathname.replace(/\/$/, "")}/mcp`;
  }

  return url.toString();
}

function normalizeBaseUrl(rawValue) {
  const candidate = (rawValue ?? "").trim();
  const url = new URL(candidate);
  url.pathname = url.pathname.replace(/\/$/, "");
  url.search = "";
  url.hash = "";
  return url.toString().replace(/\/$/, "");
}

function normalizeHex(value, fallback = "#1f2937") {
  const text = compactText(value);
  if (!text) {
    return fallback;
  }

  if (/^#[0-9a-fA-F]{6}$/.test(text)) {
    return text;
  }

  if (/^[0-9a-fA-F]{6}$/.test(text)) {
    return `#${text}`;
  }

  return fallback;
}

function round(value, digits = 1) {
  const number = toNumber(value);
  const factor = 10 ** digits;
  return Math.round(number * factor) / factor;
}

function toNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function compactText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function excerpt(value, maxLength = 140) {
  const text = compactText(value);
  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength - 1).trimEnd()}...`;
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function firstNonEmpty(...values) {
  for (const value of values) {
    const text = compactText(value);
    if (text) {
      return text;
    }
  }

  return "";
}

function periodLabel(period) {
  return PERIOD_LABELS[period] ?? "Custom period";
}

function formatMonthLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric",
  }).format(date);
}

function formatDateLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return compactText(value);
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function canonicalizeMediaUrl(url) {
  const rawUrl = compactText(url);
  if (!rawUrl) {
    return null;
  }

  if (rawUrl.startsWith("data:")) {
    return rawUrl;
  }

  try {
    const parsed = new URL(rawUrl, PUBLIC_BASE_URL);
    if (!["http:", "https:"].includes(parsed.protocol)) {
      return null;
    }

    if (LEGACY_MEDIA_HOSTS.has(parsed.hostname)) {
      const cdnUrl = new URL(MEDIA_CDN_BASE_URL);
      parsed.protocol = cdnUrl.protocol;
      parsed.host = cdnUrl.host;
    }

    return parsed.toString();
  } catch {
    return null;
  }
}

function proxyMediaUrl(url) {
  const normalizedUrl = canonicalizeMediaUrl(url);
  if (!normalizedUrl) {
    return null;
  }

  if (normalizedUrl.startsWith("data:")) {
    return normalizedUrl;
  }

  try {
    const parsed = new URL(normalizedUrl);
    if (parsed.origin === PUBLIC_BASE_ORIGIN || parsed.origin === MEDIA_CDN_ORIGIN) {
      return parsed.toString();
    }

    return `${PUBLIC_BASE_URL}/media?url=${encodeURIComponent(parsed.toString())}`;
  } catch {
    return null;
  }
}

function proxiedImageList(values) {
  return asList(values).map(proxyMediaUrl).filter(Boolean);
}

function makeReply(text, structuredContent) {
  return {
    content: [{ type: "text", text }],
    structuredContent,
  };
}

function errorReply(title, error, request = {}) {
  const message =
    error instanceof Error ? error.message : compactText(String(error));

  return makeReply(`${title}: ${message}`, {
    type: "error",
    title,
    message,
    request,
  });
}

function extractToolText(result) {
  return asList(result?.content)
    .filter((block) => block?.type === "text")
    .map((block) => compactText(block.text))
    .filter(Boolean)
    .join("\n")
    .trim();
}

function normalizeBackendResult(result) {
  if (result?.structuredContent !== undefined && result?.structuredContent !== null) {
    const payload = result.structuredContent;
    if (
      typeof payload === "object" &&
      payload !== null &&
      "result" in payload &&
      Object.keys(payload).length === 1
    ) {
      return payload.result;
    }

    return payload;
  }

  const text = extractToolText(result);
  if (!text) {
    return null;
  }

  try {
    const payload = JSON.parse(text);
    if (
      typeof payload === "object" &&
      payload !== null &&
      "result" in payload &&
      Object.keys(payload).length === 1
    ) {
      return payload.result;
    }

    return payload;
  } catch {
    return text;
  }
}

async function withBackendClient(run) {
  const transport = new StreamableHTTPClientTransport(
    new URL(BACKEND_MCP_URL)
  );
  const client = new Client({
    name: "fashion-trends-chatgpt-ui",
    version: "1.1.0",
  });

  try {
    await client.connect(transport);
    return await run(client);
  } finally {
    await transport.terminateSession().catch(() => {});
    await client.close().catch(() => {});
  }
}

async function callBackendTool(name, args = {}) {
  return withBackendClient(async (client) => {
    const result = await client.callTool({ name, arguments: args });
    if (result.isError) {
      throw new Error(extractToolText(result) || `Backend tool "${name}" failed.`);
    }

    return normalizeBackendResult(result);
  });
}

function buildFilterState(args = {}) {
  return {
    category: compactText(args.category) || null,
    gender: compactText(args.gender) || null,
    time_period: compactText(args.time_period) || null,
    source_filter: compactText(args.source_filter) || null,
    keywords: compactText(args.keywords) || null,
    metric: compactText(args.metric) || null,
  };
}

function buildColorTrendsReply(args, rows) {
  const colors = asList(rows).map((row, index) => ({
    rank: toNumber(row.trend_rank, index + 1),
    name: firstNonEmpty(row.color_family, row.pantone_name, "Unknown"),
    pantone_name: compactText(row.pantone_name),
    pantone_code: compactText(row.pantone_code),
    hex: normalizeHex(row.hex_code, "#d97757"),
    trend_score: round(row.total_trend_score, 1),
    total_impact: toNumber(row.total_impact),
    contribution_percent: round(row.contribution_percent, 1),
    post_count: toNumber(row.post_count),
    sample_images: proxiedImageList(row.sample_images),
    sample_permalinks: asList(row.sample_permalinks),
  }));

  const leader = colors[0];
  const contextBits = [
    args.category ? `${args.category}` : null,
    args.gender ? `${args.gender}` : null,
    periodLabel(args.time_period),
  ].filter(Boolean);
  const context = contextBits.length ? ` for ${contextBits.join(" / ")}` : "";

  const text = leader
    ? `Top color family${context} is ${leader.name} at ${leader.contribution_percent}% contribution across ${leader.post_count} posts.`
    : `No color trend data found${context}.`;

  return makeReply(text, {
    type: "color_trends",
    title: "Color Momentum",
    request: args,
    filters: buildFilterState(args),
    period_label: periodLabel(args.time_period),
    colors,
    leader,
  });
}

function toPostCard(row) {
  const apparel = firstNonEmpty(row.apparel_name, row.apparel_type);
  const fabric = firstNonEmpty(row.woven_fabric_type, row.knitted_fabric_type);
  const author = firstNonEmpty(row.handle, row.userName, row.brandName, "Unknown");

  return {
    id: firstNonEmpty(row.meta_postId, String(row.postId ?? "")),
    author,
    handle: compactText(row.handle),
    brand_name: compactText(row.brandName),
    user_name: compactText(row.userName),
    description: excerpt(row.description, 150),
    category: compactText(row.category),
    gender: compactText(row.gender),
    region: compactText(row.region),
    post_date: compactText(row.postDate),
    post_date_label: formatDateLabel(row.postDate),
    likes: toNumber(row.numeric_likes),
    trend_score: round(row.trend_score, 1),
    impact: toNumber(row.impact),
    image_url: proxyMediaUrl(row.image_link),
    permalink: compactText(row.permalink),
    pantone_name: compactText(row.tac_pantone_name),
    hex: normalizeHex(row.tac_hexcode, "#d5d5d5"),
    apparel,
    print_name: compactText(row.print_name),
    fabric,
  };
}

function buildPostGridReply(args, rows, options = {}) {
  const posts = asList(rows).map(toPostCard);
  const averageScore = posts.length
    ? round(
        posts.reduce((sum, post) => sum + toNumber(post.trend_score), 0) /
          posts.length,
        1
      )
    : 0;
  const topPost = posts[0] ?? null;
  const title = options.title ?? "Trending Posts";
  const view = options.view ?? "trending_posts";
  const queryLabel = options.queryLabel ?? null;

  const text = topPost
    ? `${title}: ${posts.length} posts found. The leading post is from ${topPost.author} with ${Math.round(topPost.likes).toLocaleString()} likes.`
    : `${title}: no posts found.`;

  return makeReply(text, {
    type: "post_grid",
    title,
    view,
    request: args,
    filters: buildFilterState(args),
    query_label: queryLabel,
    summary: {
      post_count: posts.length,
      average_trend_score: averageScore,
      top_likes: topPost ? topPost.likes : 0,
    },
    posts,
  });
}

function buildEntityRankingsReply(args, rows) {
  const entityLabel = args.entity_type === "influencers" ? "Influencers" : "Brands";
  const entities = asList(rows).map((row, index) => ({
    rank: index + 1,
    name: firstNonEmpty(row.name, "Unknown"),
    handle: compactText(row.handle),
    post_count: toNumber(row.post_count),
    total_trend_score: round(row.total_trend_score, 1),
    sample_images: proxiedImageList(row.sample_images),
    sample_permalinks: asList(row.sample_permalinks),
  }));
  const leader = entities[0] ?? null;
  const text = leader
    ? `Top ${entityLabel.toLowerCase()} in ${periodLabel(args.time_period)} is ${leader.name} with ${leader.post_count} posts and a total trend score of ${leader.total_trend_score}.`
    : `No ${entityLabel.toLowerCase()} found for the selected filters.`;

  return makeReply(text, {
    type: "entity_rankings",
    title: `Top ${entityLabel}`,
    request: args,
    filters: buildFilterState(args),
    entity_type: args.entity_type,
    entities,
    leader,
  });
}

function buildTrendBreakdownReply(args, rows, options) {
  const items = asList(rows).map((row) => ({
    label: firstNonEmpty(
      row.apparel,
      row.print_pattern,
      row.fabric_type,
      "Unknown"
    ),
    post_count: toNumber(row.post_count),
    total_trend_score: round(row.total_trend_score, 1),
    sample_images: proxiedImageList(row.sample_images),
    sample_permalinks: asList(row.sample_permalinks),
  }));
  const leader = items[0] ?? null;
  const text = leader
    ? `${options.title}: ${leader.label} leads with ${leader.post_count} posts and a trend score of ${leader.total_trend_score}.`
    : `${options.title}: no records found.`;

  return makeReply(text, {
    type: "trend_breakdown",
    title: options.title,
    kind: options.kind,
    request: args,
    filters: buildFilterState(args),
    items,
    leader,
  });
}

function buildDatabaseOverviewReply(args, payload) {
  const overall = payload?.overall_stats ?? {};
  const categoryDistribution = asList(payload?.category_distribution).slice(0, 8);
  const genderDistribution = asList(payload?.gender_distribution).slice(0, 5);

  const text = `Database overview: ${Math.round(
    toNumber(overall.total_unique_posts)
  ).toLocaleString()} unique posts, ${Math.round(
    toNumber(overall.total_brands)
  ).toLocaleString()} brands, and ${Math.round(
    toNumber(overall.total_influencers)
  ).toLocaleString()} influencers.`;

  return makeReply(text, {
    type: "database_overview",
    title: "Fashion Trend Dataset",
    request: args,
    filters: buildFilterState(args),
    overall_stats: overall,
    category_distribution: categoryDistribution,
    gender_distribution: genderDistribution,
  });
}

function buildTimeComparisonReply(args, payload) {
  const metric = payload?.metric ?? args.metric;
  const rows = asList(payload?.comparison_data);

  if (metric === "posts") {
    const series = [...rows]
      .sort((left, right) => new Date(left.month) - new Date(right.month))
      .map((row) => ({
        month: compactText(row.month),
        month_label: formatMonthLabel(row.month),
        post_count: toNumber(row.post_count),
        avg_trend_score: round(row.avg_trend_score, 2),
        total_likes: toNumber(row.total_likes),
        prev_month_posts: toNumber(row.prev_month_posts),
        growth_percent:
          row.growth_percent === null || row.growth_percent === undefined
            ? null
            : round(row.growth_percent, 2),
      }));
    const latest = series[series.length - 1] ?? null;
    const text = latest
      ? `Post momentum in ${latest.month_label}: ${latest.post_count} unique posts with an average trend score of ${latest.avg_trend_score}.`
      : "No month-over-month post comparison data found.";

    return makeReply(text, {
      type: "time_comparison",
      title: "Trend Momentum",
      metric,
      mode: "series",
      request: args,
      filters: buildFilterState(args),
      series,
      latest,
    });
  }

  const grouped = new Map();
  for (const row of rows) {
    const month = compactText(row.month);
    if (!grouped.has(month)) {
      grouped.set(month, []);
    }

    grouped.get(month).push({
      rank: toNumber(row.rank),
      label: firstNonEmpty(
        row.color,
        row.apparel_name,
        row.brand,
        row.print_name,
        "Unknown"
      ),
      post_count: toNumber(row.post_count),
      total_trend_score:
        row.total_trend_score === undefined
          ? null
          : round(row.total_trend_score, 2),
    });
  }

  const periods = [...grouped.entries()]
    .sort((left, right) => new Date(left[0]) - new Date(right[0]))
    .map(([month, items]) => ({
      month,
      month_label: formatMonthLabel(month),
      items: items.sort((left, right) => left.rank - right.rank),
    }));

  const latestPeriod = periods[periods.length - 1] ?? null;
  const latestLeader = latestPeriod?.items?.[0] ?? null;
  const metricLabel = metric.charAt(0).toUpperCase() + metric.slice(1);
  const text = latestLeader
    ? `${metricLabel} comparison for ${latestPeriod.month_label}: ${latestLeader.label} is currently leading.`
    : `No comparison data found for ${metricLabel.toLowerCase()}.`;

  return makeReply(text, {
    type: "time_comparison",
    title: `${metricLabel} Over Time`,
    metric,
    mode: "ranked",
    request: args,
    filters: buildFilterState(args),
    periods,
    latest_period: latestPeriod,
  });
}

function buildQueryResultReply(args, payload) {
  const rows = Array.isArray(payload) ? payload : payload ? [payload] : [];
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row ?? {})))];
  const previewRows = rows.slice(0, 20);
  const text = `${rows.length} row${rows.length === 1 ? "" : "s"} returned from the SQL query.`;

  return makeReply(text, {
    type: "query_result",
    title: "SQL Query Result",
    request: {
      sql_query: excerpt(args.sql_query, 240),
    },
    row_count: rows.length,
    columns,
    rows: previewRows,
    truncated: rows.length > previewRows.length,
  });
}

function registerToolWithErrorBoundary(server, name, config, callback) {
  registerAppTool(
    server,
    name,
    {
      ...config,
      _meta: widgetMeta,
    },
    async (args) => {
      try {
        return await callback(args);
      } catch (error) {
        return errorReply(config.title ?? name, error, args);
      }
    }
  );
}

function createFashionTrendsServer() {
  const server = new McpServer({
    name: "fashion-trends-ui",
    version: "1.1.0",
  });

  registerAppResource(
    server,
    "fashion-trends-widget",
    WIDGET_URI,
    {
      _meta: widgetResourceMeta,
    },
    async () => ({
      contents: [
        {
          uri: WIDGET_URI,
          mimeType: RESOURCE_MIME_TYPE,
          text: widgetHtml,
          _meta: widgetResourceMeta,
        },
      ],
    })
  );

  registerToolWithErrorBoundary(
    server,
    "get_color_trends",
    {
      title: "Get color trends",
      description:
        "Analyze leading color families in the fashion dataset and render a visual color momentum card.",
      inputSchema: {
        category: z.string().optional().describe("Optional category filter."),
        gender: genderEnum.optional().default("Women"),
        time_period: timePeriodEnum.optional().default("last_month"),
        limit: z.number().int().min(1).max(20).optional().default(8),
      },
    },
    async (args) => {
      const rows = await callBackendTool("get_color_trends", args);
      return buildColorTrendsReply(args, rows);
    }
  );

  registerToolWithErrorBoundary(
    server,
    "get_trending_posts",
    {
      title: "Get trending posts",
      description:
        "Return the most trend-relevant posts for the selected category and render them as a visual post wall.",
      inputSchema: {
        category: z.string().optional().describe("Optional category filter."),
        gender: genderEnum.optional().default("Women"),
        time_period: timePeriodEnum.optional().default("last_month"),
        limit: z.number().int().min(1).max(24).optional().default(12),
      },
    },
    async (args) => {
      const rows = await callBackendTool("get_trending_posts", args);
      return buildPostGridReply(args, rows, {
        title: "Trending Posts",
        view: "trending_posts",
      });
    }
  );

  registerToolWithErrorBoundary(
    server,
    "get_top_brands_or_influencers",
    {
      title: "Get top brands or influencers",
      description:
        "Rank brands or influencers by trend score and post count, then render a leaderboard.",
      inputSchema: {
        entity_type: entityTypeEnum.optional().default("brands"),
        category: z.string().optional().describe("Optional category filter."),
        time_period: timePeriodEnum.optional().default("last_month"),
        source_filter: sourceFilterEnum.optional(),
        limit: z.number().int().min(1).max(20).optional().default(10),
      },
    },
    async (args) => {
      const rows = await callBackendTool(
        "get_top_brands_or_influencers",
        args
      );
      return buildEntityRankingsReply(args, rows);
    }
  );

  registerToolWithErrorBoundary(
    server,
    "get_apparel_trends",
    {
      title: "Get apparel trends",
      description:
        "Show the top apparel silhouettes or names for the selected slice of the dataset.",
      inputSchema: {
        apparel_type_filter: z
          .string()
          .optional()
          .describe("Optional partial apparel type match."),
        category: z.string().optional().describe("Optional category filter."),
        gender: genderEnum.optional().default("Women"),
        time_period: timePeriodEnum.optional().default("last_month"),
        group_by: z.enum(["apparel_type", "apparel_name"]).optional().default("apparel_name"),
        limit: z.number().int().min(1).max(20).optional().default(10),
      },
    },
    async (args) => {
      const rows = await callBackendTool("get_apparel_trends", args);
      return buildTrendBreakdownReply(args, rows, {
        title: "Apparel Trends",
        kind: "apparel",
      });
    }
  );

  registerToolWithErrorBoundary(
    server,
    "get_print_pattern_trends",
    {
      title: "Get print or pattern trends",
      description:
        "Break down the most important print families or print names and render a ranked visual grid.",
      inputSchema: {
        category: z.string().optional().describe("Optional category filter."),
        gender: genderEnum.optional().default("Women"),
        time_period: timePeriodEnum.optional().default("last_month"),
        group_by: z.enum(["print_family", "print_name"]).optional().default("print_name"),
        limit: z.number().int().min(1).max(20).optional().default(10),
      },
    },
    async (args) => {
      const rows = await callBackendTool("get_print_pattern_trends", args);
      return buildTrendBreakdownReply(args, rows, {
        title: "Print and Pattern Trends",
        kind: "print_pattern",
      });
    }
  );

  registerToolWithErrorBoundary(
    server,
    "get_fabric_trends",
    {
      title: "Get fabric trends",
      description:
        "Rank woven, knitted, or combined fabric signals and render them in a trend breakdown card.",
      inputSchema: {
        fabric_type: z.enum(["woven", "knitted", "any"]).optional().default("any"),
        category: z.string().optional().describe("Optional category filter."),
        gender: genderEnum.optional().default("Women"),
        time_period: timePeriodEnum.optional().default("last_month"),
        limit: z.number().int().min(1).max(20).optional().default(10),
      },
    },
    async (args) => {
      const rows = await callBackendTool("get_fabric_trends", args);
      return buildTrendBreakdownReply(args, rows, {
        title: "Fabric Trends",
        kind: "fabric",
      });
    }
  );

  registerToolWithErrorBoundary(
    server,
    "get_database_statistics",
    {
      title: "Get database statistics",
      description:
        "Return a high-level overview of the fashion trend dataset and render summary distributions.",
      inputSchema: {},
    },
    async (args) => {
      const payload = await callBackendTool("get_database_statistics", args);
      return buildDatabaseOverviewReply(args, payload);
    }
  );

  registerToolWithErrorBoundary(
    server,
    "search_posts_by_keywords",
    {
      title: "Search posts by keyword",
      description:
        "Search captions and hashtags for a keyword, then render the matching posts.",
      inputSchema: {
        keywords: z.string().min(1).describe("Keywords to search for."),
        category: z.string().optional().describe("Optional category filter."),
        gender: genderEnum.optional(),
        time_period: timePeriodEnum.optional().default("last_3_months"),
        limit: z.number().int().min(1).max(24).optional().default(12),
      },
    },
    async (args) => {
      const rows = await callBackendTool("search_posts_by_keywords", args);
      return buildPostGridReply(args, rows, {
        title: "Keyword Search",
        view: "search_results",
        queryLabel: args.keywords,
      });
    }
  );

  registerToolWithErrorBoundary(
    server,
    "compare_time_periods",
    {
      title: "Compare time periods",
      description:
        "Compare post, color, apparel, brand, or print momentum across recent months and render the trend change.",
      inputSchema: {
        metric: z.enum(["posts", "colors", "apparel", "brands", "prints"]),
        category: z.string().optional().describe("Optional category filter."),
        gender: genderEnum.optional(),
      },
    },
    async (args) => {
      const payload = await callBackendTool("compare_time_periods", args);
      return buildTimeComparisonReply(args, payload);
    }
  );

  registerToolWithErrorBoundary(
    server,
    "execute_custom_sql",
    {
      title: "Execute custom SQL",
      description:
        "Run a read-only SQL query against trend_analysis_mv and render a preview table.",
      inputSchema: {
        sql_query: z
          .string()
          .min(1)
          .describe("A SELECT or WITH query against trend_analysis_mv."),
      },
    },
    async (args) => {
      const payload = await callBackendTool("execute_custom_sql", args);
      return buildQueryResultReply(args, payload);
    }
  );

  return server;
}

function resolveStaticRequestPath(pathname) {
  const requestedPath = decodeURIComponent(pathname.replace("/static/", ""));
  if (!requestedPath) {
    return null;
  }

  const resolvedPath = resolve(STATIC_DIR, requestedPath);
  const relativePath = relative(STATIC_DIR, resolvedPath);
  if (
    !relativePath ||
    relativePath.startsWith("..") ||
    relativePath.includes("\0")
  ) {
    return null;
  }

  return resolvedPath;
}

function getMimeType(filePath) {
  switch (extname(filePath).toLowerCase()) {
    case ".png":
      return "image/png";
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".webp":
      return "image/webp";
    case ".gif":
      return "image/gif";
    case ".svg":
      return "image/svg+xml";
    case ".mp4":
      return "video/mp4";
    case ".webm":
      return "video/webm";
    default:
      return "application/octet-stream";
  }
}

async function proxyRemoteMedia(req, res, url) {
  const source = url.searchParams.get("url");
  if (!source) {
    res.writeHead(400).end("Missing media URL");
    return;
  }

  let target;
  try {
    const normalizedSource = canonicalizeMediaUrl(source);
    if (!normalizedSource) {
      throw new Error("Invalid media URL");
    }
    target = new URL(normalizedSource);
  } catch {
    res.writeHead(400).end("Invalid media URL");
    return;
  }

  if (!["http:", "https:"].includes(target.protocol)) {
    res.writeHead(400).end("Unsupported media protocol");
    return;
  }

  try {
    const response = await fetch(target, {
      headers: {
        "User-Agent": "fashion-trends-ui/1.1.0",
      },
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok || !response.body) {
      res.writeHead(502).end("Upstream media request failed");
      return;
    }

    const contentType =
      response.headers.get("content-type") ?? "application/octet-stream";
    const cacheControl =
      response.headers.get("cache-control") ?? "public, max-age=300";

    res.writeHead(200, {
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": cacheControl,
      "Content-Type": contentType,
    });

    for await (const chunk of response.body) {
      res.write(chunk);
    }
    res.end();
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unable to proxy media";
    res.writeHead(502).end(message);
  }
}

const httpServer = createServer(async (req, res) => {
  if (!req.url) {
    res.writeHead(400).end("Missing URL");
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host ?? "localhost"}`);

  if (req.method === "OPTIONS" && url.pathname === MCP_PATH) {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "content-type, mcp-session-id",
      "Access-Control-Expose-Headers": "Mcp-Session-Id",
    });
    res.end();
    return;
  }

  if (req.method === "GET" && url.pathname === "/") {
    res
      .writeHead(200, { "content-type": "text/plain; charset=utf-8" })
      .end("Fashion Trends ChatGPT UI bridge");
    return;
  }

  if (req.method === "GET" && url.pathname === "/health") {
    res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    res.end(
      JSON.stringify({
        status: "ok",
        port: PORT,
        backend_mcp_url: BACKEND_MCP_URL,
      })
    );
    return;
  }

  if (
    req.method === "GET" &&
    (url.pathname === "/preview" || url.pathname === "/test-harness.html")
  ) {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(testHarnessHtml);
    return;
  }

  if (req.method === "GET" && url.pathname === "/widget/app.html") {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(widgetHtml);
    return;
  }

  if (req.method === "GET" && url.pathname === "/media") {
    await proxyRemoteMedia(req, res, url);
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/static/")) {
    const filePath = resolveStaticRequestPath(url.pathname);
    if (!filePath) {
      res.writeHead(400).end("Invalid static path");
      return;
    }

    if (!existsSync(filePath)) {
      res.writeHead(404).end("Static file not found");
      return;
    }

    const stat = statSync(filePath);
    if (!stat.isFile()) {
      res.writeHead(400).end("Invalid static path");
      return;
    }

    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Cache-Control", "public, max-age=3600");
    res.setHeader("Content-Type", getMimeType(filePath));
    res.writeHead(200, { "Content-Length": stat.size });
    createReadStream(filePath).pipe(res);
    return;
  }

  const MCP_METHODS = new Set(["POST", "GET", "DELETE"]);
  if (url.pathname === MCP_PATH && req.method && MCP_METHODS.has(req.method)) {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Expose-Headers", "Mcp-Session-Id");

    const server = createFashionTrendsServer();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
    });

    res.on("close", () => {
      transport.close().catch(() => {});
      server.close().catch(() => {});
    });

    try {
      await server.connect(transport);
      await transport.handleRequest(req, res);
    } catch (error) {
      console.error("Error handling MCP request:", error);
      if (!res.headersSent) {
        res.writeHead(500).end("Internal server error");
      }
    }
    return;
  }

  res.writeHead(404).end("Not Found");
});

const serverFilePath = fileURLToPath(new URL("server.js", import.meta.url));

httpServer.listen(PORT, () => {
  console.log(`Fashion Trends ChatGPT UI bridge -> http://localhost:${PORT}${MCP_PATH}`);
  console.log(`Proxying backend MCP at ${BACKEND_MCP_URL}`);
  console.log(`Preview harness -> http://localhost:${PORT}/preview`);
  console.log("Example Claude/Desktop config:");
  console.log(`{
  "mcpServers": {
    "fashion-trends-ui": {
      "command": "node",
      "args": ["${serverFilePath.replace(/\\/g, "\\\\")}"]
    }
  }
}`);
});
