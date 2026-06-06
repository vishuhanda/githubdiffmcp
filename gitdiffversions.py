import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from requests.auth import HTTPBasicAuth

# ============================================================
# CONFIGURATION
# ============================================================

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
JIRA_URL = os.getenv("JIRA_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
REPOS_JSON = os.getenv("REPOS_JSON")

if not GITHUB_TOKEN:
    raise ValueError("GITHUB_TOKEN environment variable is not set")

OUTPUT_FILE = "./release_report.txt"

REPOSITORIES = REPOS_JSON and eval(REPOS_JSON) or [
    {
        "owner": "jci-products",
        "repo": "acvs-jci-osp-api-gateway-services",
        "base": "1.1.38",
        "head": "1.1.43"
    },
    {
        "owner": "jci-products",
        "repo": "acvs-osp-device-management",
        "base": "1.0.918",
        "head": "1.0.921"
    }
   ,
   {
        "owner": "jci-products",
        "repo": "acvs-osp-1vms-plugin",
        "base": "1.0.343",
        "head": "1.0.346"
    } 
]


# ============================================================
# CLEAN JIRA DESCRIPTION
# ============================================================

def extract_jira_and_description(commit_title: str):
    """
    Example:
    Merge pull request #479 from
    jci-products/A1-42930-LoginSSO-returns-HTTP-500-on-invalid-credentials

    Output:
    A1-42930
    LoginSSO returns HTTP 500 on invalid credentials
    """

    jira_match = re.search(r"(A\d+-\d+)", commit_title)

    if not jira_match:
        # No Jira ticket found — return placeholders for jira and issue_type
        return "N/A", "Unknown", commit_title

    jira_ticket = jira_match.group(1)

    description = commit_title

    # Remove merge PR prefix
    description = re.sub(
        r"Merge pull request #\d+ from ",
        "",
        description,
        flags=re.IGNORECASE
    )

    # Remove repository path
    if "/" in description:
        description = description.split("/")[-1]

    # Remove Jira ID
    description = re.sub(
        rf"{jira_ticket}-?",
        "",
        description,
        flags=re.IGNORECASE
    )

    # Replace hyphens with spaces
    description = description.replace("-", " ")

    # Normalize whitespace
    description = " ".join(description.split())

    issue_type = get_issue_type(jira_ticket)

    return jira_ticket, issue_type, description 


def get_issue_type(ticket):

#     url = "https://jciproducts.atlassian.net/rest/api/3/issue/A1-40474"

#     payload = {}
#     headers = {
#   'Accept': 'application/json',
#   'Authorization': '••••••',
#     }

# response = requests.request("GET", url, headers=headers, data=payload)

# https://jciproducts.atlassian.net/rest/api/3/issue/A1-40474

  url = f"{JIRA_URL}/rest/api/3/issue/{ticket}"

  response = requests.get(
        url,
        auth=HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json"}
    )
  if response.status_code != 200:
        return "Unknown"

  data = response.json()
  return data["fields"]["issuetype"]["name"]

# ============================================================
# FETCH COMMITS
# ============================================================

def fetch_commits(repo_info):

    owner = repo_info["owner"]
    repo = repo_info["repo"]
    base = repo_info["base"]
    head = repo_info["head"]

    print(f"[Downloading] {owner}/{repo} ({base} -> {head})")

    url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repo}/compare/{base}...{head}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=60
        )

        if response.status_code != 200:
            return {
                "repo": f"{owner}/{repo}",
                "status": "error",
                "base": base,
                "head": head,
                "commits": []
            }

        compare_data = response.json()

        commits = []

        for commit in compare_data.get("commits", []):

            title = (
                commit.get("commit", {})
                .get("message", "")
                .split("\n")[0]
                .strip()
            )

            jira_ticket, issue_type, description = (
                extract_jira_and_description(title)
            )

            # Skip commits without Jira ticket
            if not jira_ticket:
                continue

            commits.append({
                "jira": jira_ticket,
                "issue_type": issue_type,
                "description": description
            })

        return {
            "repo": f"{owner}/{repo}",
            "base": base,
            "head": head,
            "status": "success",
            "commits": commits
        }

    except Exception as ex:

        return {
            "repo": f"{owner}/{repo}",
            "base": base,
            "head": head,
            "status": f"exception: {str(ex)}",
            "commits": []
        }


# ============================================================
# WRITE REPORT
# ============================================================

def write_master_report(results):

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as report:

        for result in results:

            report.write("\n")
            report.write("=" * 120 + "\n")
            report.write(
                f"REPOSITORY : {result['repo']}\n"
            )
            report.write(
                f"COMPARE    : {result['base']} --> {result['head']}\n"
            )
            report.write(
                f"STATUS     : {result['status'].upper()}\n"
            )
            report.write("=" * 120 + "\n\n")

            report.write(
                f"{'JIRA TICKET':<20}"
                f"{'ISSUE TYPE':<20}"
                f"{'DESCRIPTION'}\n"
            )

            report.write("-" * 120 + "\n")

            if not result["commits"]:
                report.write(
                    "No Jira-related commits found.\n\n"
                )
                continue

            # Remove duplicate Jira entries
            seen = set()

            for commit in result["commits"]:

                key = (
                    commit["jira"],
                    commit["description"]
                )

                if key in seen:
                    continue

                seen.add(key)

                report.write(
                    f"{commit['jira']:<20}"
                    f"{commit['issue_type']:<20}"
                    f"{commit['description']}\n"
                )

            report.write("\n\n")


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        f"Processing "
        f"{len(REPOSITORIES)} repositories..."
    )

    with ThreadPoolExecutor(max_workers=5) as executor:

        results = list(
            executor.map(
                fetch_commits,
                REPOSITORIES
            )
        )

    write_master_report(results)

    print("\nReport generated successfully.")
    print(f"Output file: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()