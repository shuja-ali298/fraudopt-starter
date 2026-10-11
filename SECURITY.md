# Security

This repository is a public research demonstration. Only anonymised historical
prediction outputs and aggregate public complaint trends belong in the dashboard
snapshot. Private transaction records, customer data and credentials must not be
published in GitHub Pages assets or Git history.

## Reporting

Use the repository's **Security → Report a vulnerability** option if private
vulnerability reporting is enabled. Avoid putting credentials or sensitive data
in public issues. The maintainer is `@shuja-ali298`.

## Maintainer controls

- Review dependency alerts and the weekly Security checks workflow. Refresh
  related dependency locks together and run tests before merging updates.
- Keep Actions pinned to full commit SHAs and review Dependabot updates.
- Protect `main`, require successful checks, and restrict the `github-pages`
  environment to `main` in GitHub settings.
- Enable secret scanning, push protection and private vulnerability reporting
  where available. `.gitignore` does not scan files or remove historical secrets.
- Store any optional cloud credentials in GitHub secrets, never in the repo.
  The current application does not require Azure to run.
- Configure additional Streamlit output directories only through the trusted
  `FRAUDOPT_OUTPUT_DIR` server environment variable. Visitors can select only
  approved sources; files cannot escape those locations through symlinks.

CodeQL results and GitHub-side protections require the workflows/settings to be
active on GitHub. Local tests and a passing dependency audit are useful checks,
not a guarantee that all vulnerabilities are absent.
