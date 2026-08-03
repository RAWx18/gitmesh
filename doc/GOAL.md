# GitMesh Agents

**GitMesh Agents is the backbone of the autonomous economy.** We are building the infrastructure that autonomous AI projects run on. Our milestone is for GitMesh Agents-powered projects to collectively generate economic output that rivals the GDP of the world's largest countries. Every decision we make should serve that: make autonomous projects more capable, more governable, more scalable, and more real.

## The Vision

Autonomous projects - AI workforces organized with real structure, governance, and accountability - will become a major force in the global economy. Not one project. Thousands. Millions. An entire economic layer that runs on AI labor, coordinated through GitMesh Agents.

GitMesh Agents is not the project. GitMesh Agents is what makes the projects possible. We are the control plane, the nervous system, the operating layer. Every autonomous project needs structure, task management, cost control, milestone alignment, and human governance. That's us. We are to autonomous projects what the corporate operating system is to human ones - except this time, the operating system is real software, not metaphor.

The measure of our success is not whether one project works. It's whether GitMesh Agents becomes the default foundation that autonomous projects are built on - and whether those projects, collectively, become a serious economic force that rivals the output of nations.

## The Problem

Task management software doesn't go far enough. When your entire workforce is AI agents, you need more than a to-do list - you need a **control plane** for an entire project.

## What This Is

GitMesh Agents is the command, communication, and control plane for a project of AI agents. It is the single place where you:

- **Manage agents as employees**: enable, organize, and track who does what
- **Define org structure**: org charts that agents themselves operate within
- **Track work in real time**: see at any moment what every agent is working on
- **Control costs**: token salary budgets per agent, spend tracking, burn rate
- **Align to milestones**: agents see how their work serves the bigger mission
- **Store project knowledge**: a shared brain for the organization

## Architecture

Two layers:

### 1. Control Plane (this software)

The central nervous system. Manages:

- Agent registry and org chart
- Task assignment and status
- Budget and token spend tracking
- Project knowledge base
- Milestone hierarchy (project → team → agent → task)
- Heartbeat monitoring - know when agents are alive, idle, or stuck

### 2. Execution Services (adapters)

Agents run externally and report into the control plane. An agent is just Python code that gets kicked off and does work. Adapters connect different execution environments:

- **Gateway**: initial adapter target
- **Heartbeat loop**: simple custom Python that loops, checks in, does work
- **Others**: any runtime that can call an API

The control plane doesn't run agents. It orchestrates them. Agents run wherever they run and phone home.

## Core Principle

You should be able to look at GitMesh Agents and understand your entire project at a glance - who's doing what, how much it costs, and whether it's working.
