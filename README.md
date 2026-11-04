# Rocklin Votes — Chrome-only GitHub Pages publishing guide

Updated November 3, 2026. **No Git installation, PowerShell, or Python on your laptop is necessary.** Use Windows File Explorer and Chrome. The ZIP includes all six school-board candidate photos embedded in `index.html`, verified starting results for Rocklin Unified Trustee Areas 2, 4, and 5, and Measure D, and a GitHub Actions workflow that checks Placer County's posted election PDF.

## Step 1 — Extract the package

1. Download `Rocklin_Votes_GitHub_CHROME.zip` from ChatGPT.
2. In Windows File Explorer, right-click the ZIP and choose **Extract All**, then **Extract**.
3. Open the extracted folder. You should see `index.html`, `latest.json`, `history.json`, `requirements.txt`, `README.md`, `.gitignore`, and the folders `scripts`, `tests`, `.github`. Do **not** upload the ZIP itself or the outer folder one level too high.

## Step 2 — Create the GitHub repository in Chrome

1. Open Chrome and sign into <https://github.com>.
2. Open <https://github.com/new>.
3. Set **Repository name** to `rocklin-votes`.
4. Choose **Public**. GitHub Pages is available for public repositories on the free plan.
5. Leave **Add a README**, **Add .gitignore**, and **Choose a license** unchecked. (Our ZIP includes the appropriate files.)
6. Click **Create repository**.

## Step 3 — Upload all extracted files using Chrome

1. On the newly created GitHub repository page, click the link **uploading an existing file**, or choose **Add file → Upload files** if you see that button.
2. In Windows File Explorer, go **inside** the extracted folder so that `index.html` is visible. Press **Ctrl+A** to select its contents, including the `.github` folder. Drag the selected items into Chrome's **Drag files here to add them to your repository** area. GitHub supports dragging folders into its uploader.
3. On GitHub's upload screen, confirm that `index.html`, `latest.json`, `history.json`, `requirements.txt`, the two files under `scripts/`, and **`.github/workflows/rocklin-votes.yml`** are present or included in the upload. The leading dot on `.github` is essential.
4. Type a commit message, e.g. `Add Rocklin Votes election dashboard`.
5. Choose **Commit directly to the main branch** if GitHub offers the choice, then click **Commit changes** (or **Propose changes**, depending on the UI). If GitHub creates a pull request instead, merge it into `main` before proceeding.
6. After the repository loads, confirm `index.html` appears at the top level (not inside an extra `Rocklin_Votes_Chrome_Upload` folder). Click `.github` → `workflows` → `rocklin-votes.yml` to verify the updater is present.

**If the `.github` folder did not upload:** On your repository's **Code** tab, click **Add file → Create new file**. In the filename field, enter exactly `.github/workflows/rocklin-votes.yml`. Open the same file from the extracted package in Windows Notepad, copy all its contents, and paste into GitHub's editor. Select **Commit changes** to `main`. GitHub will create both missing folders automatically from that filename.

## Step 4 — Enable GitHub Pages

1. On the repository, open **Settings** (near the top; if hidden use the `...` overflow menu).
2. In the sidebar under **Code and automation**, click **Pages**.
3. Under **Build and deployment → Source**, select **GitHub Actions**. There is no branch/folder dropdown to set when using this option.
4. Don't choose a suggested Jekyll or static HTML template workflow: this package already provides `rocklin-votes.yml`.

## Step 5 — Run the data check and publish the site

1. Go to the repository's **Actions** tab.
2. If GitHub asks whether to enable workflows on the repository, approve it.
3. In the left sidebar, select **Rocklin Votes - Update and Publish**.
4. Click **Run workflow**, keep branch **main**, then click the green **Run workflow** button.
5. Open the new workflow run. A **green checkmark** on `update-and-publish` indicates the workflow completed. If red, expand the failing step to read its error.
6. Return to **Settings → Pages** and click **Visit site** after GitHub publishes it. Your address normally looks like `https://YOUR-USERNAME.github.io/rocklin-votes/`.

## Step 6 — Confirm the website and Refresh button

1. Open the *public GitHub Pages URL*, **not** the `index.html` file from your Downloads folder.
2. Verify that all **six candidate photos** appear: Saathoff and Sutherland (Area 2); Hoehne and Makis (Area 4); Counter and Boyce (Area 5).
3. Verify Measure D shows the Yes/No percentages and 55% approval threshold.
4. Look at the `County report` date. These are unofficial county results, updated when a newer PDF is successfully parsed.
5. Click **Refresh results**. The button immediately requests the newest `latest.json` file published to your GitHub Pages URL (with cache bypass). **It does not immediately run the county PDF scraper**; to force that, return to **Actions** and use **Run workflow** again.
6. The supplied GitHub Actions job also runs on an approximately **five-minute schedule**, subject to GitHub scheduling delays and the timing of new county reports. The page checks for updated published data while open.

You can also open `https://YOUR-USERNAME.github.io/rocklin-votes/latest.json` in Chrome to inspect the published vote figures directly.

## Step 7 — Share with Facebook and friends

Copy the public GitHub Pages link from Chrome's address bar. Paste **that link**, not the ZIP or an `index.html` file from your laptop, into a Facebook post, Messenger, text message, or email. People who open the link see the same updated dashboard. Facebook may cache the thumbnail preview; the vote totals update **on the webpage**, not inside the Facebook post itself.

## Troubleshooting

- **There is no Actions workflow listed:** The hidden `.github/workflows/rocklin-votes.yml` file wasn't uploaded or isn't on `main`. Use the browser-only recovery in Step 3.
- **The Actions job cannot push updated `latest.json`:** Under **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions** and save, then run the workflow again. The repository or organization may enforce tighter permissions.
- **The Pages job fails:** Confirm **Settings → Pages → Source = GitHub Actions**. Review the latest Actions run for the exact failing step.
- **The site opens but doesn't update:** Open the latest Actions run and check the county PDF fetch / parse result. The website intentionally retains the last verified vote totals if a download fails or an older zero report is returned.
- **The public link returns 404:** Verify the GitHub Actions publishing job completed successfully and that GitHub Pages is enabled. Recheck **Settings → Pages** for the exact URL.
- **You only see HTML without photos or results:** Make sure you opened the GitHub Pages `Visit site` URL, not a GitHub file preview or a local HTML attachment.

### Important technical limitations

This is a static public website with an automated server-side GitHub Actions updater. The on-page **Refresh results** button can only fetch results already published by the workflow; it can't force a new PDF check by itself. GitHub Actions scheduled jobs are not guaranteed to execute at the exact minute scheduled. A live GitHub deployment cannot be verified until you upload and run this workflow in your account. The site is not a government website and vote totals remain unofficial until certified.

Official results: <https://www.placercountyelections.gov/election-results/>
GitHub docs for uploads: <https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository>
GitHub docs for Pages workflows: <https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site>
