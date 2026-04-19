import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Zambia Remit",
  description: "Send and track money transfers to Zambia.",
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
