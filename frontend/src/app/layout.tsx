import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Analizador de Archivos Inteligente",
  description: "Gobernanza de Datos con IA · Powered by Gemini - Por Alexander Espina Leyton",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
