<div align="center">

<picture>
   <source srcset="public/logo/light_logo.png" media="(prefers-color-scheme: dark)">
   <img src="public/logo/dark_logo.png" alt="GitMesh Logo" width="250">
</picture>

**AI-powered Git collaboration network for OSS**

[![OpenSource License](https://img.shields.io/badge/License-Apache%20License-orange.svg?style=for-the-badge)](LICENSE.md)
[![Contributors](https://img.shields.io/github/contributors/LF-Decentralized-Trust-Mentorships/gitmesh.svg?style=for-the-badge&logo=git)](https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh/graphs/contributors)
[![Under Development](https://img.shields.io/badge/Status-Under%20Development-yellow.svg?style=for-the-badge)](#)
[![Join Discord](https://img.shields.io/badge/Join%20us%20on-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/FkrWfGtZn3)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/10972/badge)](https://www.bestpractices.dev/projects/10972)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/LF-Decentralized-Trust-Mentorships/gitmesh/badge)](https://scorecard.dev/viewer/?uri=github.com/LF-Decentralized-Trust-Mentorships/gitmesh)

*Code with purpose, Integrate with confidence*

[![Documentation](https://img.shields.io/badge/Documentation-000000?style=flat&logo=github)](https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh/README.md) 
[![Join Community](https://img.shields.io/badge/Join_Community-000000?style=flat&logo=discord)](https://discord.gg/FkrWfGtZn3)
[![Join Waitlist](https://img.shields.io/badge/Join_Waitlist-000000?style=flat&logo=github)](https://www.gitmesh.dev) 

</div>

---

## </> What is GitMesh?

<div align="center">
   <a href="https://youtu.be/j5ZdorkZVgU" target="_blank">
      <img src="https://img.youtube.com/vi/j5ZdorkZVgU/maxresdefault.jpg" alt="Watch the video" width="350" style="max-width:100%; border-radius:8px;"/>
   </a>
   <br>
   <sub><em>Click the video above to watch demo!</em></sub>
   <br></br>
</div>


**GitMesh** is a Git collaboration network designed to solve open source's biggest challenge: contributor dropout. Our AI-powered platform provides real-time branch-level insights, intelligent contributor-task matching, and automated workflows. It transforms complex codebases into clear, guided contribution journeys—fueling engagement with gamified rewards, bounties, and integration with popular open source support programs.

Our mascot (Meshy/Mesh Wolf) reflects GitMesh’s core: agile, resilient, and unstoppable together. Like a pack, we thrive on teamwork — efficient, and powerful in unison.

---

## </> Meet us at

<div align="center">
   <table>
      <tr>
         <td align="center">
            <img src="public/os_japan.avif" alt="Coming Soon" width="300" style="max-width:100%; border-radius:8px; opacity:0.7;"/>
            <br>
            <sub><em>OpenSource Summit Japan • 8-10 Dec 2025</em></sub>
         </td>
         <td align="center">
            <img src="public/os_korea.avif" alt="Coming Soon" width="300" style="max-width:100%; border-radius:8px; opacity:0.7;"/>
            <br>
            <sub><em>OpenSource Summit Korea • 4-5 Nov 2025</em></sub>
         </td>
      </tr>
   </table>
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
- HashiCorp Vault
   <details>
   <summary>Linux (.deb)</summary>

   ```bash
   sudo apt-get update && sudo apt-get install -y gnupg software-properties-common
   wget -O- https://apt.releases.hashicorp.com/gpg | \
   gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg

   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
   https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
   sudo tee /etc/apt/sources.list.d/hashicorp.list

   sudo apt update
   sudo apt install vault
   ````

   </details>

   <details>
   <summary>Linux (.rpm)</summary>

   ```bash
   sudo yum install -y yum-utils
   sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
   sudo yum install vault
   ```

   </details>

   <details>
   <summary>macOS</summary>

   ```bash
   brew tap hashicorp/tap
   brew install hashicorp/tap/vault
   ```

   </details>

   <details>
   <summary>Windows</summary>

   Download from: [https://developer.hashicorp.com/vault/downloads](https://developer.hashicorp.com/vault/downloads)

   Or:

   ```powershell
   choco install vault
   # or
   scoop install vault
   ```

   </details>

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


### 👾 Running the Application

1. **Start HashiCorp Vault** (in first terminal)
   ```bash
   vault server -dev # Keep this running
   ```
   
   **In another terminal:**
   ```bash
   export VAULT_ADDR='http://127.0.0.1:8200'
   export VAULT_TOKEN=your-root-token  # Copy from "vault server -dev" output
   vault secrets enable transit
   ```

2. **Start Python Backend** (in second terminal)
   ```bash
   cd backend
   ```

   <details>
   <summary>Linux/Mac</summary>

   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   ```

   </details>
   <details>
   <summary>Windows</summary>

   ```bash
   python3.12 -m venv venv
   .\venv\Scripts\activate
   ```

   </details>

   ```bash
   pip install -r requirements.txt
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Start Frontend** (in third terminal)
   ```bash
   cd ui
   npm install
   npm run dev
   ```

> **Access the Application**
>   - Frontend: http://localhost:3000
>   - Vault UI: http://127.0.0.1:8200


---

## </> Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

[![Complete Roadmap](https://img.shields.io/badge/View%20our-Roadmap-blue?style=for-the-badge&logo=github&logoColor=white)](https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh/blob/main/ROADMAP.md)

### 👾 Quick Contributing Steps:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a signed pull request

Mesh & Meshy are excited to see what amazing contributions you'll bring to the GitMesh community!

---

## </> Our Maintainers

<style>
/* Optional: Center the entire table content */
.maintainer-table {
  display: flex;
  justify-content: center;
}

/* Style for the container of each maintainer */
.maintainer-card {
  /* Set a slight transition for a smooth "pop" effect */
  transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
  border-radius: 8px; /* Slightly rounded corners */
  padding: 10px;
  margin: 10px;
  text-align: center;
  /* Initial state: slightly subtle box shadow */
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

/* Hover effect: Scale up and make the shadow more prominent */
.maintainer-card:hover {
  transform: scale(1.05); /* Zoom in slightly */
  box-shadow: 0 8px 15px rgba(0, 0, 0, 0.2); /* Deeper shadow */
  /* You can even change the background color on hover if you like, e.g., background-color: #f0f0f0; */
}

/* Style for the avatar image */
.maintainer-avatar {
  border-radius: 50%; /* Make the image perfectly round */
  border: 4px solid transparent; /* Initial border */
  transition: border-color 0.2s ease-in-out;
}

/* Hover effect for the avatar */
.maintainer-card:hover .maintainer-avatar {
  /* Give it a subtle highlight color on hover, like a project-specific blue */
  border-color: #0077B5; /* Using LinkedIn's blue for example */
}

/* Style for the social links */
.maintainer-links a {
  display: inline-block;
  margin: 3px;
  /* Subtle link transition */
  transition: transform 0.1s ease-in-out;
}

/* Hover effect for the social links */
.maintainer-links a:hover {
  transform: translateY(-2px); /* Makes the badge "lift" */
}
</style>

<div class="maintainer-table">
  <div class="maintainer-card">
    <a href="https://github.com/RAWx18">
      <img class="maintainer-avatar" src="https://avatars.githubusercontent.com/RAWx18?s=150" width="120" alt="RAWx18"/><br/>
      <sub><b>RAWx18</b></sub>
    </a>
    <br/>
    <div class="maintainer-links">
      <a href="https://github.com/RAWx18">
        <img src="https://img.shields.io/badge/GitHub-100000?style=flat&logo=github&logoColor=white" />
      </a>
      <a href="https://linkedin.com/in/RAWx18">
        <img src="https://img.shields.io/badge/LinkedIn-0077B5?style=flat&logo=linkedin&logoColor=white" />
      </a>
      <a href="mailto:rawx18@example.com">
        <img src="https://img.shields.io/badge/Email-D14836?style=flat&logo=gmail&logoColor=white" />
      </a>
    </div>
  </div>
  
  <div class="maintainer-card">
    <a href="https://github.com/parvm1102">
      <img class="maintainer-avatar" src="https://avatars.githubusercontent.com/parvm1102?s=150" width="120" alt="parvm1102"/><br/>
      <sub><b>parvm1102</b></sub>
    </a>
    <br/>
    <div class="maintainer-links">
      <a href="https://github.com/parvm1102">
        <img src="https://img.shields.io/badge/GitHub-100000?style=flat&logo=github&logoColor=white" />
      </a>
      <a href="https://linkedin.com/in/parvm1102">
        <img src="https://img.shields.io/badge/LinkedIn-0077B5?style=flat&logo=linkedin&logoColor=white" />
      </a>
      <a href="mailto:parvm1102@example.com">
        <img src="https://img.shields.io/badge/Email-D14836?style=flat&logo=gmail&logoColor=white" />
      </a>
    </div>
  </div>
  
  <div class="maintainer-card">
    <a href="https://github.com/Ronit-Raj9">
      <img class="maintainer-avatar" src="https://avatars.githubusercontent.com/Ronit-Raj9?s=150" width="120" alt="Ronit-Raj9"/><br/>
      <sub><b>Ronit-Raj9</b></sub>
    </a>
    <br/>
    <div class="maintainer-links">
      <a href="https://github.com/Ronit-Raj9">
        <img src="https://img.shields.io/badge/GitHub-100000?style=flat&logo=github&logoColor=white" />
      </a>
      <a href="https://linkedin.com/in/Ronit-Raj9">
        <img src="https://img.shields.io/badge/LinkedIn-0077B5?style=flat&logo=linkedin&logoColor=white" />
      </a>
      <a href="mailto:ronit.raj9@example.com">
        <img src="https://img.shields.io/badge/Email-D14836?style=flat&logo=gmail&logoColor=white" />
      </a>
    </div>
  </div>
</div>


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

<br></br>

<div align="center">
  <a href="https://www.star-history.com/#LF-Decentralized-Trust-Mentorships/gitmesh&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=LF-Decentralized-Trust-Mentorships/gitmesh&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=LF-Decentralized-Trust-Mentorships/gitmesh&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=LF-Decentralized-Trust-Mentorships/gitmesh&type=Date" width="700" />
  </picture>
</a>
</div>

---

<br></br>
<a href="https://www.lfdecentralizedtrust.org/">
  <img src="https://www.lfdecentralizedtrust.org/hubfs/LF%20Decentralized%20Trust/lfdt-horizontal-white.png" alt="Supported by the Linux Foundation Decentralized Trust" width="220"/>
</a>

**Supported by the [Linux Foundation Decentralized Trust](https://www.lfdecentralizedtrust.org/)** – Advancing open source innovation.
