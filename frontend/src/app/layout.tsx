import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AEGIS-Marine | Maritime Forensic Intelligence & Spill Attribution",
  description:
    "Autonomous satellite surveillance, Lagrangian trajectory hindcasting, and AIS candidate vessel correlation platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen bg-brand-teal-deep text-white font-sans antialiased selection:bg-brand-green selection:text-brand-teal-deep">
        <TooltipProvider delayDuration={150}>
          {children}
        </TooltipProvider>
      </body>
    </html>
  );
}
