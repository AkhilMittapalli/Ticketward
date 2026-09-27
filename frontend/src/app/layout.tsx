import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ticketward",
  description:
    "Human-in-the-loop customer-support resolution copilot (portfolio demo, synthetic data).",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <div className="flex-1">{children}</div>
        <footer className="border-t border-black/10 px-6 py-4 text-xs text-neutral-600 dark:border-white/15 dark:text-neutral-400">
          {/* Spec §3 disclaimer. TODO(P6/P8, D-05): add "Built with Llama" here once Llama
              Prompt Guard 2 ships. */}
          Taskmoor is fictional and not affiliated with any real company. All companies, customers,
          accounts and tickets shown here are synthetic.
        </footer>
      </body>
    </html>
  );
}
