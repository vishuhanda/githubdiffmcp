import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool,
} from "@modelcontextprotocol/sdk/types.js";
import axios from "axios";

/**
 * Create MCP Server
 */
const server = new Server(
  {
    name: "github-diff-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

/**
 * List available tools
 */
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "git_changes_between_versions",
        description:
          "Get GitHub commit changes between two versions or tags of a repository",
        inputSchema: {
          type: "object",
          properties: {
            repo: {
              type: "string",
              description: "Repository in owner/repo format",
            },
            fromVersion: {
              type: "string",
              description: "Older/base version or tag",
            },
            toVersion: {
              type: "string",
              description: "Newer/target version or tag",
            },
          },
          required: ["repo", "fromVersion", "toVersion"],
        },
      },
    ] as Tool[],
  };
});

/**
 * Handle tool execution
 */
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  if (!args) {
    throw new Error("Arguments are required for this tool");
  }

  const { repo, fromVersion, toVersion } = args as { repo: string; fromVersion: string; toVersion: string };

  try {
    const [owner, repoName] = repo.split("/");

    if (!owner || !repoName) {
      throw new Error("Invalid repo format. Use owner/repo");
    }

    const url = `https://api.github.com/repos/${owner}/${repoName}/compare/${fromVersion}...${toVersion}`;

    const response = await axios.get(url, {
      headers: {
        Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
      },
    });

    const commits = response.data.commits
      .filter((c: any) => !c.commit.message.startsWith("Merge"))
      .map((c: any) => ({
        sha: c.sha.substring(0, 7),
        author: c.commit.author.name,
        message: c.commit.message.split("\n")[0],
        url: c.html_url,
      }));

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({
            repository: repo,
            fromVersion,
            toVersion,
            totalCommits: commits.length,
            commits,
          }, null, 2),
        },
      ],
    };
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : "Unknown error occurred";
    return {
      content: [
        {
          type: "text" as const,
          text: `Error: ${errorMessage}`,
        },
      ],
      isError: true,
    };
  }
});

/**
 * Start Server
 */
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("GitHub Diff MCP Server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
