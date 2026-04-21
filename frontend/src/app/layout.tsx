import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MbongoPay",
  description: "Send and track cross-border money transfers.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
