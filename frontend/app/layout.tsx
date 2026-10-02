// The frame every page sits in: font, drifting background, top bar.

import type { Metadata } from "next";
import { Bricolage_Grotesque } from "next/font/google";
import Background from "@/components/Background";
import Nav from "@/components/Nav";
import "./globals.css";

// One variable font for everything (FRONTEND_RULES.md §2).
const bricolage = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage" });

export const metadata: Metadata = {
  title: "PRISM: ask your finance and medical files",
  description: "Ask questions about finance and medical documents and see exactly which sources each answer came from.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={bricolage.variable}>
      <body className="min-h-dvh">
        <Background />
        <Nav />
        {children}
      </body>
    </html>
  );
}
