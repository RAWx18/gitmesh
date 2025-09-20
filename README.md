<div align="center">

<picture>
   <source srcset="public/logo/light_logo.png" media="(prefers-color-scheme: dark)">
   <img src="public/logo/dark_logo.png" alt="GitMesh Logo" width="250">
</picture>

**The Next-Generation Git Collaboration Platform**

*Transforming Open Source Development with Branch-Level Collaboration*

[![OpenSource License](https://img.shields.io/badge/License-Apache%20License-orange.svg?style=for-the-badge)](LICENSE.md)
[![Contributors](https://img.shields.io/github/contributors/LF-Decentralized-Trust-Mentorships/gitmesh.svg?style=for-the-badge&logo=git)](https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh/graphs/contributors)
[![Under Development](https://img.shields.io/badge/Status-Under%20Development-yellow.svg?style=for-the-badge)](#)
[![Join Discord](https://img.shields.io/badge/Join%20us%20on-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/FkrWfGtZn3)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/10972/badge)](https://www.bestpractices.dev/projects/10972)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/LF-Decentralized-Trust-Mentorships/gitmesh/badge)](https://scorecard.dev/viewer/?uri=github.com/LF-Decentralized-Trust-Mentorships/gitmesh)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Ffossas%2Ffossa-cli.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Ffossas%2Ffossa-cli?ref=badge_shield)

[**Documentation**](https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh/README.md) • [**Join Community**](https://discord.gg/FkrWfGtZn3)

</div>

---

## </> What is GitMesh?

**GitMesh** revolutionizes Git-based collaboration by introducing **Branch-Level Management** — a paradigm shift that transforms how teams plan, develop, and contribute to open-source projects. Unlike traditional project management tools, GitMesh organizes your codebase at the branch level, providing streamlined contribution tracking and seamless workflow orchestration.

Our friendly mascot here represents the core philosophy of GitMesh: small, efficient, but incredibly powerful when working together in a team!

GitMesh is ready to revolutionize the open source world with improved collaboration and branch management.

[Waitlist website](gitmesh.vercel.app)

---

## </> Key Features

<div align="center">

### 👾 **Git Collaboration Platform**
```
┌─────────────────────────────────────────────────────────────┐
│     Branch Management                                       │
│     PR Visualization                                        │
│     Issue Management                                        │
│     Code Collaboration Tools                                │
│     Repository Organization                                 │
│     Open Source Contribution Management                     │
└─────────────────────────────────────────────────────────────┘
```

### 🧠 **AI-Powered Code Intelligence**
```
┌─────────────────────────────────────────────────────────────┐
│     Cosmos AI Integration                                   │
│     Intelligent Code Analysis                               │
│     Multi-Model AI Support (GPT-4, Claude, Gemini)         │
│     Real-time Code Review                                   │
│     Automated Documentation                                 │
│     Smart Code Generation                                   │
└─────────────────────────────────────────────────────────────┘
```

### 👾 **Easy Workflow Management**
```
┌─────────────────────────────────────────────────────────────┐
│     Branch-Specific Planning                                │
│     Help opensource contributors know what's important      │
│     Automated Status Tracking                               │
│     Custom Workflow Templates                               │
└─────────────────────────────────────────────────────────────┘
```

### 👾 **Analytics & Insights**
```
┌─────────────────────────────────────────────────────────────┐
│     Contribution Heatmaps                                   │
│     Velocity Tracking                                       │
│     See who's working on which issue/PR                     │
│     Team Performance Dashboards                             │
│     Showcase skills & avoid conflicts                       │
└─────────────────────────────────────────────────────────────┘
```

### 👾 **Enterprise Integration**
```
┌─────────────────────────────────────────────────────────────┐
│     Multi-Platform Support (GitHub, GitLab, Bitbucket)      │
│     SSO Authentication                                      │
│     Team Collaboration Features                             │
│     Webhook Automation                                      │
└─────────────────────────────────────────────────────────────┘
```

</div>

---

<div align="center">

## </> **Why Choose Our Platform?**

| **Efficient** | **Fast** | **Collaborative** | **Secure** |
|:---:|:---:|:---:|:---:|
| Data-driven insights | Lightning fast responses | Team-first approach | Enterprise-grade security |
| Branch visualization | Real-time updates | Conflict-free workflows | SSO & compliance ready |

</div>

---

## </> Quick Start

<div align="center">
<picture>
   <source srcset="public/mascott/meshy.png" media="(prefers-color-scheme: dark)">
   <img src="public/mascott/mesh.png" alt="GitMesh Logo" width="250">
</picture>
</div>

### 👾 Prerequisites

- Node.js v18+ and npm
- Python 3.12
- Git

### 👾 Clone the repository
   ```bash
   git clone https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh
   cd gitmesh
   ```


### 👾 Environment Variables

> Python Backend Configuration

```bash
cp backend/.env.example backend/.env
```

> Frontend Configuration

```bash
cp ui/.env.example ui/.env
```

> **Note**: Replace all placeholder values [REDACTED] with your actual configuration values.

### 👾 Installation

1. **Setup HashiCorp Vault (Required for Key Management)**
   
   **Install Vault:**
   ```bash
   # On Linux/macOS via Homebrew
   brew install vault
   
   # Or download from https://www.vaultproject.io/downloads
   ```
   
   **Start Vault Server:**
   ```bash
   vault server -dev
   
   # In another terminal, set environment variables
   export VAULT_ADDR='http://127.0.0.1:8200'
   export VAULT_TOKEN=your-root-token  # Copy from vault server output
   
   # Enable Transit secrets engine
   vault secrets enable transit
   ```
   
   **For Production:**
   ```bash
   # Create vault config file (vault.hcl)
   vault server -config=vault.hcl
   
   # Initialize and unseal vault
   vault operator init
   vault operator unseal
   ```

2. **Setup Python Backend**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Linux/Mac
   .\venv\Scripts\activate # On Windows
   pip install -r requirements.txt
   ```

3. **Setup Frontend**
   ```bash
   cd ui
   npm install
   ```

### 👾 Running the Application

1. **Start HashiCorp Vault** (in first terminal)
   ```bash
   vault server -dev
   # Note the Root Token from the output
   ```

2. **Configure Vault Environment** (in second terminal)
   ```bash
   export VAULT_ADDR='http://127.0.0.1:8200'
   export VAULT_TOKEN=your-root-token  # From step 1
   vault secrets enable transit
   ```

3. **Start Python Backend** (in third terminal)
   ```bash
   cd backend
   source venv/bin/activate  # On Linux/Mac
   .\venv\Scripts\activate # On Windows
   # Make sure VAULT_TOKEN is set in your .env file
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Start Frontend** (in fourth terminal)
   ```bash
   cd ui
   npm run dev
   ```

5. **Access the Application**
   - Frontend: http://localhost:3000
   - Vault UI: http://127.0.0.1:8200
  
### 👾 Static Demo

[Deployed on Vercel](https://GitMesh-demo.vercel.app/)

## </> Roadmap

### 👾 **Q4 2025 - Production Goals**
- ✅ Refactor and rebase codebase with proper routing architecture
- ⏳ Enhance user interface (UI) for improved usability and aesthetics
- ⏳ Implement advanced branch visualization
- ⏳ Shift complete database to cloud
- ⏳ Develop contribution tracking system
- ⏳ Strengthen security and optimize rate-limiting mechanisms
- ⏳ Containerize the application using Docker
- ⏳ Deploy the complete website to production environment
- ⏳ Set up and publish project documentation site

---

## </> Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### 👾 Quick Contributing Steps:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

Mesh & Meshy are excited to see what amazing contributions you'll bring to the GitMesh community!

---

<p align="center">
Our Awesome Contributors
</p>
<a href="https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=LF-Decentralized-Trust-Mentorships/gitmesh&max=100&columns=10" alt="GitMesh Contributors" />
</a>

---

## </> Community & Support

<div align="center">

[![Join Discord](https://img.shields.io/badge/Join%20us%20on-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/FkrWfGtZn3)

### 👾 **Support Channels**

| Channel                                                         | Typical Response Time | Best For                                             |
| --------------------------------------------------------------- | --------------------- | ---------------------------------------------------- |
| [Discord](https://discord.gg/FkrWfGtZn3)                     | Real-time             | Quick questions, community discussions               |
| [Email Support](mailto:gitmesh.oss@gmail.com)                 | 24–48 hours           | Technical issues, detailed bug reports               |
| [Twitter / X](https://x.com/gitmesh_oss)                      | Online                | Tagging the project, general updates, public reports |
| [GitHub Issues](https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh/issues) | 1–3 days              | Bug reports, feature requests, feedback              |

</div>

---

## </> Project Statistics

<div align="center">

| Metric | Value |
|--------|-------|
| **Total Commits** | ![Commits](https://img.shields.io/github/commit-activity/t/LF-Decentralized-Trust-Mentorships/gitmesh) |
| **Pull Requests** | ![PRs](https://img.shields.io/github/issues-pr/LF-Decentralized-Trust-Mentorships/gitmesh) |
| **Issues Resolved** | ![Issues](https://img.shields.io/github/issues-closed/LF-Decentralized-Trust-Mentorships/gitmesh) |
| **Latest Release** | ![Release](https://img.shields.io/github/v/release/LF-Decentralized-Trust-Mentorships/gitmesh) |

</div>

---

## </> License

This project is licensed under the Apache-2.0 License - see the [LICENSE](LICENSE) file for details.

---

## </> Acknowledgments

- All our contributors and community members
- Open source libraries that made this possible
- Beta testers and early adopters

---

## </> Star Graph: Project GitMesh

<div align="center"> <img src="https://starchart.cc/LF-Decentralized-Trust-Mentorships/gitmesh.svg" alt="Star Graph for Project GitMesh" width="600"/> <br/> <sub>✨ GitHub star history of <strong><a href="https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh" target="_blank">LF-Decentralized-Trust-Mentorships/gitmesh</a></strong></sub> </div>

---

<br></br>
[![Supported by the Linux Foundation Decentralized Trust](https://www.lfdecentralizedtrust.org/hubfs/LF%20Decentralized%20Trust/lfdt-horizontal-white.png)](https://www.lfdecentralizedtrust.org/)

**Supported by the [Linux Foundation Decentralized Trust](https://www.lfdecentralizedtrust.org/)** – Advancing open source innovation.

---

<br></br>
<div align="center">

**Made with ❤️ by the GitMesh Team**

*Transforming the future of collaborative development, one commit at a time.*

</div>
