import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Local Data Analyst',
  description: 'Chat with your spreadsheet privately — every answer shows its work.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  )
}
