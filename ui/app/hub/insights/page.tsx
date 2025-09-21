"use client";

import { HubHeader } from "@/components/hub/HubHeader";
import { useEffect, useState, useMemo, lazy, Suspense } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { InsightCard } from "@/components/hub/insights/InsightCard";
import { GitCommit, GitPullRequest, Star, Users } from "lucide-react";
import { HubInsightsSkeleton } from "@/components/hub/insights/HubInsightsSkeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Repository } from "@/lib/github-api";

const Chart = lazy(() => import("@/components/hub/insights/Chart"));

export default function HubInsightsPage() {
  const { user, githubApi } = useAuth();
  const [summary, setSummary] = useState<any>(null);
  const [languages, setLanguages] = useState<any[]>([]);
  const [commitHistory, setCommitHistory] = useState<any[]>([]);
  const [contributors, setContributors] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("all");

  useEffect(() => {
    if (githubApi) {
      setLoading(true);
      githubApi.getUserRepositories().then((repos) => {
        setRepositories(repos);
        setLoading(false);
      });
    }
  }, [githubApi]);

  useEffect(() => {
    if (githubApi) {
      const api = githubApi;
      setLoading(true);

      const fetchInsights = async () => {
        const [summary, repos] = await Promise.all([
          api.getAggregatedSummary(),
          selectedRepo === "all" ? api.getUserRepositories() : [await api.getRepository(selectedRepo.split('/')[0], selectedRepo.split('/')[1])],
        ]);

        setSummary(summary);

        const langData = repos.reduce((acc, repo) => {
          if (repo.language) {
            const lang = acc.find((l) => l.name === repo.language);
            if (lang) {
              lang.value += 1;
            } else {
              acc.push({ name: repo.language, value: 1 });
            }
          }
          return acc;
        }, [] as { name: string; value: number }[]);
        setLanguages(langData);

        const commitPromises = repos.map((repo) =>
          api.getRepositoryCommits(repo.owner.login, repo.name)
        );
        const allCommits = await Promise.all(commitPromises);
        const flatCommits = allCommits.flat();
        const commitData = flatCommits.reduce((acc, commit) => {
          const date = new Date(commit.commit.author.date).toLocaleDateString();
          const day = acc.find((d) => d.name === date);
          if (day) {
            day.value += 1;
          } else {
            acc.push({ name: date, value: 1 });
          }
          return acc;
        }, [] as { name: string; value: number }[]);
        setCommitHistory(commitData);

        if (selectedRepo !== 'all') {
            const [owner, repoName] = selectedRepo.split('/');
            const contributorsData = await api.getRepositoryContributors(owner, repoName);
            setContributors(contributorsData);
        }

        setLoading(false);
      };

      fetchInsights();
    }
  }, [githubApi, selectedRepo]);

  const memoizedCharts = useMemo(() => (
    <Suspense fallback={<HubInsightsSkeleton />}>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <Chart data={languages} title="Language Distribution" />
        <Chart data={commitHistory} title="Commit History" />
      </div>
    </Suspense>
  ), [languages, commitHistory, contributors, selectedRepo]);

  if (loading && !summary) {
    return <HubInsightsSkeleton />;
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <div className="container mx-auto p-4 sm:p-6 lg:p-8">
        <div className="flex justify-end mb-4">
          <Select onValueChange={setSelectedRepo} defaultValue="all">
            <SelectTrigger className="w-full md:w-[280px] bg-black border-gray-700 text-white rounded-lg focus:ring-orange-500 focus:border-orange-500">
              <SelectValue placeholder="Select a repository" />
            </SelectTrigger>
            <SelectContent className="bg-black text-white border-gray-700">
              <SelectItem value="all">All Repositories</SelectItem>
              {repositories.map((repo) => (
                <SelectItem key={repo.id} value={repo.full_name}>
                  {repo.full_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {/* <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mt-6">
          <InsightCard title="Total Commits" value={summary?.totalCommits || 0} icon={<GitCommit className="h-6 w-6 text-orange-500" />} />
          <InsightCard title="Open PRs" value={summary?.openPRs || 0} icon={<GitPullRequest className="h-6 w-6 text-orange-500" />} />
          <InsightCard title="Total Stars" value={summary?.totalStars || 0} icon={<Star className="h-6 w-6 text-orange-500" />} />
          <InsightCard title="Total Collaborators" value={summary?.totalCollaborators || 0} icon={<Users className="h-6 w-6 text-orange-500" />} />
        </div> */}
        {memoizedCharts}
      </div>
    </div>
  );
}
