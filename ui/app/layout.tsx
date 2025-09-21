import { LocalStorageProvider } from "@/contexts/LocalStorageContext";
import type React from "react"
import type { Metadata } from "next"
import "./globals.css"
import { ThemeProvider } from "@/components/theme-provider"
import { AuthProvider } from "@/contexts/AuthContext"
import { RepositoryProvider } from "@/contexts/RepositoryContext"
import { BranchProvider } from "@/contexts/BranchContext"
import RateLimitHandler from "@/components/RateLimitHandler"
import Image from "next/image"

export const metadata: Metadata = {
  title: "GitMesh",
  description: "AI-powered GitHub contribution manager with structured planning and branch-aware workflows",
  icons: [
    { rel: "icon", url: "/light_logo.png", media: "(prefers-color-scheme: dark)" },
    { rel: "icon", url: "/dark_logo.png", media: "(prefers-color-scheme: light)" },
  ],
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <LocalStorageProvider>
            <AuthProvider>
              <RepositoryProvider>
                <BranchProvider>
                  <RateLimitHandler>
                    {children}
                  </RateLimitHandler>
                </BranchProvider>
              </RepositoryProvider>
            </AuthProvider>
          </LocalStorageProvider>
        </ThemeProvider>
        {process.env.NODE_ENV === 'development' && (
          <script src="/debug-auth.js" />
        )}
      </body>
    </html>
  )
}
