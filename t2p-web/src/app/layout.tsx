import type { Metadata } from "next";
import "./globals.css";
import ClientWrapper from "./ClientWrapper";

export const metadata: Metadata = {
  title: "T2P AI Mentor",
  description: "Modular Calculus Intelligent Analysis System Based on Agentic RAG",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col bg-[#F8FAFC]" suppressHydrationWarning>
        {/* Provide global user context using ClientWrapper */}
        <ClientWrapper>
          {children}
        </ClientWrapper>
      </body>
    </html>
  );
}
