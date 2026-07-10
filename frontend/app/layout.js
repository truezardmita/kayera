import { Outfit } from "next/font/google";
import "./globals.css";

const outfit = Outfit({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
});

export const metadata = {
  title: "Keyra Store Admin Dashboard",
  description: "Dashboard admin untuk mengelola bot telegram dan payment gateway pakasir",
};

export default function RootLayout({ children }) {
  return (
    <html lang="id">
      <body className={outfit.className}>{children}</body>
    </html>
  );
}
