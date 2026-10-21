import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Data Analyst",
  description: "Connect data sources and explore your data with AI-powered analysis.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
