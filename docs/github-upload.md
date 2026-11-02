# Publish this project to GitHub

The project is published at [Ksiuhl/multilingual-prompt-optimizer](https://github.com/Ksiuhl/multilingual-prompt-optimizer).
These steps explain how to publish a separate copy under your own account.

## With Git

1. Sign in to [GitHub](https://github.com/new) and create a repository named
   `multilingual-prompt-optimizer`. Choose public or private. Create an empty
   repository without adding another README, license, or gitignore.
2. Open a terminal in this extracted project folder. If Git was not preserved by
   the archive, initialize it:

```bash
git init -b main
git add .
git commit -m "Initial prompt optimizer prototype"
```

3. Replace `YOUR_USERNAME` below with your GitHub username, then run:

```bash
git remote add origin https://github.com/YOUR_USERNAME/multilingual-prompt-optimizer.git
git push -u origin main
```

Git may ask you to sign in using your normal GitHub authentication. Once pushed,
open the Actions tab to see the configured tests run. Local checks do not mean that
the hosted workflow has already passed.

## With the GitHub website

Create the empty repository, choose **uploading an existing file**, and upload the
extracted project's contents. Upload the files and folders, not just the ZIP.
Ensure the `.github/workflows/ci.yml` file is included if you want automated checks.

The README, license, attribution, examples, and datasets are ready to include.
Model weights, tokenizer vocabulary files, cached dependencies, and local chat
artifacts are deliberately excluded.
