"use client";

import { useState, useEffect } from "react";
import {
  LayoutDashboard,
  FolderTree,
  Package,
  Receipt,
  Settings,
  LogOut,
  Key,
  Coins,
  Plus,
  Pencil,
  Trash2,
  X,
  Menu,
  ShieldCheck,
  CreditCard,
  Bot,
  Megaphone
} from "lucide-react";

const API_BASE = typeof window !== "undefined" && window.location.port === "3000"
  ? "http://localhost:8000"
  : "";

export default function AdminDashboard() {
  // Auth state
  const [token, setToken] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [usernameInput, setUsernameInput] = useState("");
  const [passwordInput, setPasswordInput] = useState("");

  // Navigation
  const [activeTab, setActiveTab] = useState("home"); // home, categories, products, settings, transactions, broadcast
  const [broadcastMessage, setBroadcastMessage] = useState("");

  // Data states
  const [stats, setStats] = useState(null);
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [settings, setSettings] = useState({});
  const [transactions, setTransactions] = useState([]);

  // Modal / Form states
  const [modalType, setModalType] = useState(null); // 'add_category', 'add_product', 'edit_product', 'manage_stock'
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [stockItems, setStockItems] = useState([]);
  const [bulkStockText, setBulkStockText] = useState("");
  
  // Modals Input fields
  const [categoryName, setCategoryName] = useState("");
  const [categorySlug, setCategorySlug] = useState("");
  const [productName, setProductName] = useState("");
  const [productCategoryId, setProductCategoryId] = useState("");
  const [productPrice, setProductPrice] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [productActive, setProductActive] = useState(true);

  // Settings fields
  const [settingsForm, setSettingsForm] = useState({
    telegram_bot_token: "",
    bot_active: "false",
    bot_welcome_msg: "",
    bot_contact_admin: "",
    pakasir_slug: "",
    pakasir_api_key: "",
    admin_username: "",
    admin_password: "",
  });

  // UI state
  const [loading, setLoading] = useState(false);
  const [toasts, setToasts] = useState([]);

  // Add a toast notification helper
  const showToast = (message, type = "success") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  // Mount logic: read token
  useEffect(() => {
    const savedToken = localStorage.getItem("keyra_admin_token");
    if (savedToken) {
      setToken(savedToken);
    }
  }, []);

  // Fetching data
  const fetchData = async () => {
    if (!token) return;
    try {
      const headers = { Authorization: `Bearer ${token}` };

      // Stats
      const resStats = await fetch(API_BASE + "/api/admin/stats", { headers });
      if (resStats.status === 401) {
        handleLogout();
        return;
      }
      const dataStats = await resStats.json();
      setStats(dataStats);

      // Categories
      const resCats = await fetch(API_BASE + "/api/admin/categories", { headers });
      const dataCats = await resCats.json();
      setCategories(Array.isArray(dataCats) ? dataCats : []);

      // Products
      const resProds = await fetch(API_BASE + "/api/admin/products", { headers });
      const dataProds = await resProds.json();
      setProducts(Array.isArray(dataProds) ? dataProds : []);

      // Settings
      const resSettings = await fetch(API_BASE + "/api/admin/settings", { headers });
      const dataSettings = await resSettings.json();
      setSettings(dataSettings);
      setSettingsForm(dataSettings);

      // Transactions
      const resTxs = await fetch(API_BASE + "/api/admin/transactions", { headers });
      const dataTxs = await resTxs.json();
      setTransactions(Array.isArray(dataTxs) ? dataTxs : []);

    } catch (err) {
      console.error("Error fetching admin dashboard data:", err);
      showToast("Gagal memuat data dari server.", "error");
    }
  };

  // Poll stats and transactions every 5 seconds for real-time sales feel
  useEffect(() => {
    if (token) {
      fetchData();
      const interval = setInterval(fetchData, 5000);
      return () => clearInterval(interval);
    }
  }, [token]);

  // Broadcast: Send Message
  const handleSendBroadcast = async (e) => {
    e.preventDefault();
    if (!broadcastMessage.trim()) {
      showToast("Pesan broadcast tidak boleh kosong.", "error");
      return;
    }
    
    setLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/admin/broadcast", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ message: broadcastMessage })
      });
      
      const data = await res.json();
      if (res.ok && data.success) {
        showToast(data.message || "Broadcast berhasil dikirim!", "success");
        setBroadcastMessage("");
      } else {
        showToast(data.detail || "Gagal mengirim broadcast.", "error");
      }
    } catch (err) {
      console.error(err);
      showToast("Koneksi gagal saat mengirim broadcast.", "error");
    } finally {
      setLoading(false);
    }
  };

  // Auth: Login
  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch(API_BASE + "/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: usernameInput, password: passwordInput }),
      });
      const data = await res.json();
      if (res.status === 200 && data.success) {
        localStorage.setItem("keyra_admin_token", data.token);
        setToken(data.token);
        showToast("Login Berhasil!");
      } else {
        showToast(data.detail || "Username atau Password salah", "error");
      }
    } catch (err) {
      showToast("Koneksi ke server gagal.", "error");
    } finally {
      setLoading(false);
    }
  };

  // Auth: Logout
  const handleLogout = () => {
    localStorage.removeItem("keyra_admin_token");
    setToken(null);
    setStats(null);
    setMobileMenuOpen(false);
    showToast("Anda telah keluar dari sistem.");
  };

  // Action: Add Category
  const handleAddCategory = async (e) => {
    e.preventDefault();
    if (!categoryName || !categorySlug) return;
    try {
      const res = await fetch(API_BASE + "/api/admin/categories", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name: categoryName, slug: categorySlug }),
      });
      const data = await res.json();
      if (res.status === 200 && data.success) {
        showToast("Kategori berhasil ditambahkan!");
        setModalType(null);
        setCategoryName("");
        setCategorySlug("");
        fetchData();
      } else {
        showToast(data.detail || "Gagal menambahkan kategori.", "error");
      }
    } catch (err) {
      showToast("Error saat menghubungi server.", "error");
    }
  };

  // Action: Delete Category
  const handleDeleteCategory = async (catId) => {
    if (!confirm("Apakah Anda yakin ingin menghapus kategori ini? Semua produk dalam kategori ini juga akan terhapus.")) return;
    try {
      const res = await fetch(API_BASE + `/api/admin/categories/${catId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.status === 200 && data.success) {
        showToast("Kategori berhasil dihapus.");
        fetchData();
      } else {
        showToast(data.detail || "Gagal menghapus kategori.", "error");
      }
    } catch (err) {
      showToast("Error saat menghubungi server.", "error");
    }
  };

  // Action: Add / Edit Product
  const handleProductSubmit = async (e) => {
    e.preventDefault();
    if (!productName || !productCategoryId || !productPrice) return;
    
    const payload = {
      category_id: parseInt(productCategoryId),
      name: productName,
      description: productDescription,
      price: parseFloat(productPrice),
      is_active: productActive
    };

    try {
      const method = modalType === "add_product" ? "POST" : "PUT";
      const url = modalType === "add_product" 
        ? "/api/admin/products" 
        : `/api/admin/products/${selectedProduct.id}`;

      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (res.status === 200 && data.success) {
        showToast(modalType === "add_product" ? "Produk berhasil dibuat!" : "Produk berhasil diupdate!");
        setModalType(null);
        resetProductForm();
        fetchData();
      } else {
        showToast(data.detail || "Gagal memproses produk.", "error");
      }
    } catch (err) {
      showToast("Error saat menghubungi server.", "error");
    }
  };

  const resetProductForm = () => {
    setProductName("");
    setProductCategoryId("");
    setProductPrice("");
    setProductDescription("");
    setProductActive(true);
    setSelectedProduct(null);
  };

  const openEditProduct = (p) => {
    setSelectedProduct(p);
    setProductName(p.name);
    setProductCategoryId(p.category_id);
    setProductPrice(p.price);
    setProductDescription(p.description || "");
    setProductActive(p.is_active);
    setModalType("edit_product");
  };

  // Action: Delete Product
  const handleDeleteProduct = async (prodId) => {
    if (!confirm("Hapus produk ini? Semua stok akan ikut terhapus.")) return;
    try {
      const res = await fetch(API_BASE + `/api/admin/products/${prodId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.status === 200 && data.success) {
        showToast("Produk berhasil dihapus.");
        fetchData();
      } else {
        showToast(data.detail || "Gagal menghapus produk.", "error");
      }
    } catch (err) {
      showToast("Error.", "error");
    }
  };

  // Action: Stock Management (Fetch & Add)
  const openManageStock = async (p) => {
    setSelectedProduct(p);
    setModalType("manage_stock");
    setBulkStockText("");
    try {
      const res = await fetch(API_BASE + `/api/admin/products/${p.id}/stock`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setStockItems(Array.isArray(data) ? data : []);
    } catch (err) {
      showToast("Gagal mengambil data stok.", "error");
    }
  };

  const handleAddStock = async (e) => {
    e.preventDefault();
    if (!bulkStockText.trim()) return;
    try {
      const res = await fetch(API_BASE + `/api/admin/products/${selectedProduct.id}/stock`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ content: bulkStockText }),
      });
      const data = await res.json();
      if (res.status === 200 && data.success) {
        showToast(`Berhasil menambahkan ${data.count} data stok!`);
        openManageStock(selectedProduct); // Reload stock list
        fetchData(); // Reload products to get updated stock counts
      } else {
        showToast("Gagal menambahkan stok.", "error");
      }
    } catch (err) {
      showToast("Error.", "error");
    }
  };

  const handleDeleteStockItem = async (itemId) => {
    try {
      const res = await fetch(API_BASE + `/api/admin/products/stock/${itemId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.status === 200 && data.success) {
        showToast("Item stok berhasil dihapus.");
        openManageStock(selectedProduct); // Reload stock list
        fetchData();
      } else {
        showToast("Gagal menghapus item.", "error");
      }
    } catch (err) {
      showToast("Error.", "error");
    }
  };

  // Action: Save Settings
  const handleSettingsSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(API_BASE + "/api/admin/settings", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(settingsForm),
      });
      const data = await res.json();
      if (res.status === 200 && data.success) {
        showToast("Konfigurasi disimpan. Telegram Bot dijadwalkan untuk restart.");
        // If password was changed, the user may need to log in again with new password
        if (settingsForm.admin_password !== settings.admin_password || settingsForm.admin_username !== settings.admin_username) {
          showToast("Kredensial login berubah. Silakan login kembali.", "warning");
          setTimeout(handleLogout, 2000);
        } else {
          fetchData();
        }
      } else {
        showToast("Gagal menyimpan konfigurasi.", "error");
      }
    } catch (err) {
      showToast("Error.", "error");
    }
  };

  // Action: Simulate Transaction payment (Sandbox)
  const handleSimulatePayment = async (orderId) => {
    try {
      showToast("Mengirim simulasi pembayaran...");
      const res = await fetch(API_BASE + `/api/admin/transactions/${orderId}/simulate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.status === 200 && data.success) {
        showToast("Simulasi pembayaran berhasil! Transaksi selesai.");
        fetchData();
      } else {
        showToast(data.detail || "Gagal melakukan simulasi.", "error");
      }
    } catch (err) {
      showToast("Error.", "error");
    }
  };

  // Login view if not authenticated
  if (!token) {
    return (
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <div style={{ display: "inline-flex", justifyContent: "center", marginBottom: "16px" }}>
              <div className="logo-icon"><Key size={20} /></div>
            </div>
            <h2 className="login-title">Keyra Store</h2>
            <p className="login-subtitle">Admin Dashboard Panel</p>
          </div>
          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                type="text"
                className="form-input"
                placeholder="Masukkan username admin"
                value={usernameInput}
                onChange={(e) => setUsernameInput(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                type="password"
                className="form-input"
                placeholder="Masukkan password admin"
                value={passwordInput}
                onChange={(e) => setPasswordInput(e.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn btn-primary" style={{ width: "100%", marginTop: "10px" }} disabled={loading}>
              {loading ? "Memproses..." : "Masuk"}
            </button>
          </form>
        </div>
        <div className="toast-container">
          {toasts.map((t) => (
            <div key={t.id} className={`toast toast-${t.type}`}>
              <span>{t.message}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Dashboard layout once authenticated
  return (
    <div className="dashboard-wrapper">
      {/* Mobile Top Header */}
      <div className="mobile-topbar">
        <button className="hamburger-btn" onClick={() => setMobileMenuOpen(true)}><Menu size={24} /></button>
        <span className="logo-text" style={{ fontSize: "16px" }}>Keyra Store</span>
        <div style={{ width: "24px" }} />
      </div>

      {/* Sidebar Backdrop Overlay */}
      {mobileMenuOpen && (
        <div className="sidebar-overlay" onClick={() => setMobileMenuOpen(false)} />
      )}
      {/* Sidebar Navigation */}
      <aside className={`sidebar ${mobileMenuOpen ? "open" : ""}`}>
        <div className="logo-section">
          <div className="logo-icon"><ShieldCheck size={20} /></div>
          <span className="logo-text">Keyra Admin</span>
        </div>
        <ul className="nav-links">
          <li className={`nav-item ${activeTab === "home" ? "active" : ""}`} onClick={() => { setActiveTab("home"); setMobileMenuOpen(false); }}>
            <LayoutDashboard size={18} className="nav-icon" /> Ringkasan
          </li>
          <li className={`nav-item ${activeTab === "categories" ? "active" : ""}`} onClick={() => { setActiveTab("categories"); setMobileMenuOpen(false); }}>
            <FolderTree size={18} className="nav-icon" /> Kategori Produk
          </li>
          <li className={`nav-item ${activeTab === "products" ? "active" : ""}`} onClick={() => { setActiveTab("products"); setMobileMenuOpen(false); }}>
            <Package size={18} className="nav-icon" /> Daftar Produk
          </li>
          <li className={`nav-item ${activeTab === "transactions" ? "active" : ""}`} onClick={() => { setActiveTab("transactions"); setMobileMenuOpen(false); }}>
            <Receipt size={18} className="nav-icon" /> Riwayat Transaksi
          </li>
          <li className={`nav-item ${activeTab === "settings" ? "active" : ""}`} onClick={() => { setActiveTab("settings"); setMobileMenuOpen(false); }}>
            <Settings size={18} className="nav-icon" /> Settings / Token
          </li>
          <li className={`nav-item ${activeTab === "broadcast" ? "active" : ""}`} onClick={() => { setActiveTab("broadcast"); setMobileMenuOpen(false); }}>
            <Megaphone size={18} className="nav-icon" /> Kirim Broadcast
          </li>
        </ul>
        <div className="sidebar-footer">
          <button className="logout-btn" onClick={handleLogout} style={{ marginBottom: "12px", display: "flex", alignItems: "center", gap: "10px" }}>
            <LogOut size={16} /> Keluar Panel
          </button>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", textAlign: "center", borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "12px" }}>
            Created by <a href="https://t.me/ThunderBotXX" target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent-purple)", fontWeight: "600" }}>t.me/ThunderBotXX</a>
          </div>
        </div>
      </aside>

      {/* Main Panel */}
      <main className="main-content">
        <div className="header-container">
          <div>
            <h1 className="page-title">
              {activeTab === "home" && "Dashboard Ringkasan"}
              {activeTab === "categories" && "Manajemen Kategori"}
              {activeTab === "products" && "Manajemen Produk & Stok"}
              {activeTab === "transactions" && "Riwayat Transaksi Pelanggan"}
              {activeTab === "settings" && "Konfigurasi Bot & Payment Gateway"}
              {activeTab === "broadcast" && "Broadcast Pengumuman"}
            </h1>
            <p className="page-subtitle">
              {activeTab === "home" && "Ringkasan performa penjualan dan transaksi terbaru."}
              {activeTab === "categories" && "Buat dan atur kategori untuk mengelompokkan produk digital."}
              {activeTab === "products" && "Kelola produk digital, harga, dan input token/akun digital."}
              {activeTab === "transactions" && "Daftar invoice, status pembayaran, dan link simulation."}
              {activeTab === "settings" && "Atur token Telegram Bot, credentials Pakasir, dan kredensial admin."}
              {activeTab === "broadcast" && "Kirim pesan broadcast massal ke seluruh pengguna Telegram Bot."}
            </p>
          </div>
          {activeTab === "categories" && (
            <button className="btn btn-primary" onClick={() => { setCategoryName(""); setCategorySlug(""); setModalType("add_category"); }}>
              <Plus size={16} /> Tambah Kategori
            </button>
          )}
          {activeTab === "products" && (
            <button className="btn btn-primary" onClick={() => { resetProductForm(); setModalType("add_product"); }}>
              <Plus size={16} /> Tambah Produk
            </button>
          )}
        </div>

        {/* Tab content conditional rendering */}
        {activeTab === "home" && stats && (
          <div>
            {/* Metrics cards grid */}
            <div className="metrics-grid">
              <div className="metric-card">
                <div className="metric-header">
                  <span className="metric-title">Total Pendapatan</span>
                  <span className="metric-icon" style={{ color: "var(--accent-cyan)" }}><Coins size={20} /></span>
                </div>
                <div className="metric-value">Rp {stats.summary.total_revenue.toLocaleString()}</div>
                <div style={{ fontSize: "12px", color: "var(--success)" }}>Berdasarkan invoice completed</div>
              </div>
              <div className="metric-card">
                <div className="metric-header">
                  <span className="metric-title">Total Transaksi</span>
                  <span className="metric-icon" style={{ color: "var(--accent-purple)" }}><Receipt size={20} /></span>
                </div>
                <div className="metric-value">{stats.summary.total_transactions}</div>
                <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>{stats.summary.completed_transactions} Transaksi Sukses</div>
              </div>
              <div className="metric-card">
                <div className="metric-header">
                  <span className="metric-title">Kategori Aktif</span>
                  <span className="metric-icon" style={{ color: "var(--accent-pink)" }}><FolderTree size={20} /></span>
                </div>
                <div className="metric-value">{stats.summary.total_categories}</div>
                <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Pengelompokan fleksibel</div>
              </div>
              <div className="metric-card">
                <div className="metric-header">
                  <span className="metric-title">Produk Terdaftar</span>
                  <span className="metric-icon" style={{ color: "var(--accent-cyan)" }}><Package size={20} /></span>
                </div>
                <div className="metric-value">{stats.summary.total_products}</div>
                <div style={{ fontSize: "12px", color: "var(--accent-cyan)" }}>{stats.summary.active_products} Produk Aktif</div>
              </div>
            </div>

            {/* Charts Section */}
            <div className="charts-grid">
              {/* Daily Sales Chart */}
              <div className="chart-card">
                <h3 className="chart-title">Grafik Pendapatan Harian (Past 7 Days)</h3>
                {stats.sales_chart && stats.sales_chart.length > 0 ? (
                  <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", height: "230px", padding: "10px 0", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                    {stats.sales_chart.map((item, idx) => {
                      const maxVal = Math.max(...stats.sales_chart.map((s) => s.revenue), 1000);
                      const heightPercent = (item.revenue / maxVal) * 100;
                      return (
                        <div key={idx} style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: 1 }}>
                          <span style={{ fontSize: "10px", color: "var(--accent-cyan)", marginBottom: "6px" }}>
                            {item.revenue > 0 ? `Rp ${(item.revenue / 1000).toFixed(0)}k` : "0"}
                          </span>
                          <div
                            style={{
                              width: "45%",
                              minWidth: "20px",
                              height: `${Math.max(heightPercent, 4)}px`, // Fallback height
                              height: `${Math.max(heightPercent, 4)}%`,
                              background: "linear-gradient(180deg, var(--accent-purple) 0%, var(--accent-pink) 100%)",
                              borderRadius: "6px 6px 0 0",
                              boxShadow: "0 0 10px rgba(155, 93, 229, 0.2)",
                              transition: "height 0.5s ease"
                            }}
                          />
                          <span style={{ fontSize: "10px", color: "var(--text-secondary)", marginTop: "8px" }}>
                            {item.date.split("-").slice(1).join("/")}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "230px", color: "var(--text-muted)" }}>
                    Belum ada data penjualan harian.
                  </div>
                )}
              </div>

              {/* Category Share */}
              <div className="chart-card">
                <h3 className="chart-title">Pendapatan Per Kategori</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "10px" }}>
                  {stats.category_chart && stats.category_chart.length > 0 ? (
                    stats.category_chart.map((cat, idx) => {
                      const maxRev = Math.max(...stats.category_chart.map((c) => c.revenue), 1);
                      const percentage = (cat.revenue / maxRev) * 100;
                      return (
                        <div key={idx}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: "6px" }}>
                            <span style={{ fontWeight: "500" }}>{cat.category}</span>
                            <span style={{ color: "var(--accent-cyan)" }}>Rp {cat.revenue.toLocaleString()}</span>
                          </div>
                          <div style={{ width: "100%", height: "8px", background: "rgba(255,255,255,0.05)", borderRadius: "4px", overflow: "hidden" }}>
                            <div
                              style={{
                                width: `${percentage}%`,
                                height: "100%",
                                background: "linear-gradient(90deg, var(--accent-purple), var(--accent-pink))",
                                borderRadius: "4px"
                              }}
                            />
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div style={{ color: "var(--text-muted)", fontSize: "14px", textAlign: "center", marginTop: "40px" }}>
                      Belum ada penjualan kategori.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Recent Transactions Table */}
            <div className="table-card">
              <div className="table-header">
                <h3 style={{ fontSize: "16px", fontWeight: "600" }}>10 Transaksi Terbaru</h3>
                <button className="btn btn-secondary btn-sm" onClick={() => { setActiveTab("transactions"); setMobileMenuOpen(false); }}>Lihat Semua</button>
              </div>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Order ID</th>
                      <th>Username</th>
                      <th>Produk</th>
                      <th>Metode</th>
                      <th>Total</th>
                      <th>Status</th>
                      <th>Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.recent_transactions.map((tx) => (
                      <tr key={tx.order_id}>
                        <td style={{ fontFamily: "monospace", fontSize: "13px" }}>{tx.order_id}</td>
                        <td>@{tx.telegram_username || tx.telegram_user_id}</td>
                        <td>{tx.product_name}</td>
                        <td style={{ fontSize: "12px" }}>{tx.payment_method?.toUpperCase()}</td>
                        <td style={{ fontWeight: "500" }}>Rp {tx.total_payment.toLocaleString()}</td>
                        <td>
                          <span className={`badge badge-${tx.status}`}>{tx.status}</span>
                        </td>
                        <td>
                          {tx.status === "pending" && (
                            <button className="btn btn-primary btn-sm" onClick={() => handleSimulatePayment(tx.order_id)}>
                              <CreditCard size={12} /> Simulasi Bayar
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {stats.recent_transactions.length === 0 && (
                      <tr>
                        <td colSpan="7" style={{ textAlign: "center", color: "var(--text-muted)" }}>Belum ada transaksi.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab content: Categories */}
        {activeTab === "categories" && (
          <div className="table-card">
            <div className="table-header">
              <h3 style={{ fontSize: "16px", fontWeight: "600" }}>Daftar Kategori ({categories.length})</h3>
            </div>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Nama Kategori</th>
                    <th>Slug</th>
                    <th>Tanggal Dibuat</th>
                    <th>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {categories.map((cat) => (
                    <tr key={cat.id}>
                      <td>{cat.id}</td>
                      <td style={{ fontWeight: "600" }}>{cat.name}</td>
                      <td><code>{cat.slug}</code></td>
                      <td>{new Date(cat.created_at).toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" })}</td>
                      <td>
                        <button className="btn btn-danger btn-sm" onClick={() => handleDeleteCategory(cat.id)}>
                          <Trash2 size={12} /> Hapus
                        </button>
                      </td>
                    </tr>
                  ))}
                  {categories.length === 0 && (
                    <tr>
                      <td colSpan="5" style={{ textAlign: "center", color: "var(--text-muted)" }}>Belum ada kategori. Silakan buat kategori baru.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab content: Products */}
        {activeTab === "products" && (
          <div className="table-card">
            <div className="table-header">
              <h3 style={{ fontSize: "16px", fontWeight: "600" }}>Daftar Produk Digital ({products.length})</h3>
            </div>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Kategori</th>
                    <th>Nama Produk</th>
                    <th>Harga</th>
                    <th>Stok Tersedia</th>
                    <th>Status</th>
                    <th style={{ width: "280px" }}>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((p) => (
                    <tr key={p.id}>
                      <td>{p.id}</td>
                      <td>
                        <span style={{ fontSize: "12px", background: "rgba(255,255,255,0.06)", padding: "4px 8px", borderRadius: "6px" }}>
                          {p.category_name}
                        </span>
                      </td>
                      <td style={{ fontWeight: "600" }}>{p.name}</td>
                      <td style={{ fontWeight: "500" }}>Rp {p.price.toLocaleString()}</td>
                      <td>
                        <span style={{ fontWeight: "600", color: p.stock_count > 0 ? "var(--success)" : "var(--danger)" }}>
                          {p.stock_count} item
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-${p.is_active ? "completed" : "cancelled"}`}>
                          {p.is_active ? "Aktif" : "Nonaktif"}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: "8px" }}>
                          <button className="btn btn-secondary btn-sm" onClick={() => openManageStock(p)}>
                            <Key size={12} /> Stok
                          </button>
                          <button className="btn btn-secondary btn-sm" onClick={() => openEditProduct(p)}>
                            <Pencil size={12} /> Edit
                          </button>
                          <button className="btn btn-danger btn-sm" onClick={() => handleDeleteProduct(p.id)}>
                            <Trash2 size={12} /> Hapus
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {products.length === 0 && (
                    <tr>
                      <td colSpan="7" style={{ textAlign: "center", color: "var(--text-muted)" }}>Belum ada produk. Silakan tambahkan produk baru.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab content: Transactions */}
        {activeTab === "transactions" && (
          <div className="table-card">
            <div className="table-header">
              <h3 style={{ fontSize: "16px", fontWeight: "600" }}>Semua Riwayat Transaksi ({transactions.length})</h3>
            </div>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Order ID</th>
                    <th>User Telegram</th>
                    <th>Produk</th>
                    <th>Pembayaran</th>
                    <th>Total Bayar</th>
                    <th>Tanggal Pemesanan</th>
                    <th>Status</th>
                    <th>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx) => (
                    <tr key={tx.order_id}>
                      <td style={{ fontFamily: "monospace", fontSize: "13px" }}>{tx.order_id}</td>
                      <td>
                        <span style={{ fontWeight: "500" }}>@{tx.telegram_username || tx.telegram_user_id}</span>
                        <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>ID: {tx.telegram_user_id}</div>
                      </td>
                      <td style={{ fontWeight: "500" }}>{tx.product_name}</td>
                      <td>
                        <div style={{ fontSize: "12px", fontWeight: "600" }}>{tx.payment_method?.toUpperCase()}</div>
                        <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>Biaya: Rp {tx.fee.toLocaleString()}</div>
                      </td>
                      <td style={{ fontWeight: "600" }}>Rp {tx.total_payment.toLocaleString()}</td>
                      <td style={{ fontSize: "13px" }}>
                        {new Date(tx.created_at).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                      </td>
                      <td>
                        <span className={`badge badge-${tx.status}`}>{tx.status}</span>
                      </td>
                      <td>
                        {tx.status === "pending" && (
                          <button className="btn btn-primary btn-sm" onClick={() => handleSimulatePayment(tx.order_id)}>
                            <CreditCard size={12} /> Simulasi Bayar
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {transactions.length === 0 && (
                    <tr>
                      <td colSpan="8" style={{ textAlign: "center", color: "var(--text-muted)" }}>Belum ada data transaksi.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab content: Settings */}
        {activeTab === "settings" && (
          <form onSubmit={handleSettingsSubmit} className="settings-grid">
            {/* Telegram settings */}
            <div className="settings-card">
              <h3 style={{ fontSize: "16px", fontWeight: "600", marginBottom: "20px", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "10px" }}>
                <span style={{ display: "flex", alignItems: "center", gap: "8px" }}><Bot size={18} /> Konfigurasi Telegram Bot</span>
              </h3>
              <div className="form-group">
                <label className="form-label">Telegram Bot Token</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Masukkan Token Bot Telegram"
                  value={settingsForm.telegram_bot_token}
                  onChange={(e) => setSettingsForm({ ...settingsForm, telegram_bot_token: e.target.value })}
                />
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Token didapatkan dari @BotFather di Telegram</span>
              </div>
              <div className="form-group">
                <label className="form-label">Status Aktif Bot</label>
                <select
                  className="form-select"
                  value={settingsForm.bot_active}
                  onChange={(e) => setSettingsForm({ ...settingsForm, bot_active: e.target.value })}
                >
                  <option value="true">Aktif (Polling / Running)</option>
                  <option value="false">Nonaktif (Bot dimatikan)</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Username Admin Bot (Contact)</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="@UsernameAdmin"
                  value={settingsForm.bot_contact_admin}
                  onChange={(e) => setSettingsForm({ ...settingsForm, bot_contact_admin: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Start / Welcome Message Bot</label>
                <textarea
                  className="form-textarea"
                  value={settingsForm.bot_welcome_msg}
                  onChange={(e) => setSettingsForm({ ...settingsForm, bot_welcome_msg: e.target.value })}
                />
              </div>
            </div>

            {/* Payment & Dashboard settings */}
            <div className="settings-card" style={{ display: "flex", flexDirection: "column" }}>
              <h3 style={{ fontSize: "16px", fontWeight: "600", marginBottom: "20px", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "10px" }}>
                <span style={{ display: "flex", alignItems: "center", gap: "8px" }}><CreditCard size={18} /> Payment Gateway (Pakasir.com)</span>
              </h3>
              <div className="form-group">
                <label className="form-label">Project Slug</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Slug Proyek Pakasir"
                  value={settingsForm.pakasir_slug}
                  onChange={(e) => setSettingsForm({ ...settingsForm, pakasir_slug: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">API Key Pakasir</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="API Key Proyek Pakasir"
                  value={settingsForm.pakasir_api_key}
                  onChange={(e) => setSettingsForm({ ...settingsForm, pakasir_api_key: e.target.value })}
                />
              </div>

              <h3 style={{ fontSize: "16px", fontWeight: "600", margin: "20px 0 20px 0", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "10px" }}>
                <span style={{ display: "flex", alignItems: "center", gap: "8px" }}><Key size={18} /> Kredensial Login Dashboard</span>
              </h3>
              <div className="form-group">
                <label className="form-label">Username Dashboard</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Username Admin Dashboard"
                  value={settingsForm.admin_username}
                  onChange={(e) => setSettingsForm({ ...settingsForm, admin_username: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Password Dashboard</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="Password Admin Dashboard"
                  value={settingsForm.admin_password}
                  onChange={(e) => setSettingsForm({ ...settingsForm, admin_password: e.target.value })}
                />
              </div>

              <button type="submit" className="btn btn-primary" style={{ marginTop: "auto", alignSelf: "flex-end" }}>
                💾 Simpan Konfigurasi
              </button>
            </div>
          </form>
        )}

        {/* Tab content: Broadcast */}
        {activeTab === "broadcast" && (
          <div className="settings-card" style={{ maxWidth: "800px", margin: "0 auto" }}>
            <h3 style={{ fontSize: "16px", fontWeight: "600", marginBottom: "20px", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "10px" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "8px" }}><Megaphone size={18} /> Kirim Pesan Broadcast</span>
            </h3>
            
            <form onSubmit={handleSendBroadcast} style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
              <div className="form-group">
                <label className="form-label" style={{ marginBottom: "8px", display: "block" }}>Isi Pesan Broadcast</label>
                <textarea
                  className="form-textarea"
                  style={{ minHeight: "250px", fontFamily: "monospace", fontSize: "14px" }}
                  placeholder="Ketik pesan Anda di sini... (Mendukung format Markdown seperti *teks tebal*, _miring_, `code`, [link](http://example.com))"
                  value={broadcastMessage}
                  onChange={(e) => setBroadcastMessage(e.target.value)}
                  disabled={loading}
                  required
                />
                <div style={{ marginTop: "8px", fontSize: "12px", color: "var(--text-muted)", lineHeight: "1.5" }}>
                  💡 <strong>Catatan format Markdown:</strong><br />
                  - Ketik <code>*Teks Tebal*</code> untuk teks tebal.<br />
                  - Ketik <code>_Teks Miring_</code> untuk teks miring.<br />
                  - Pastikan semua tag markdown lengkap (punya pasangan penutup) agar bot tidak gagal parsing.
                </div>
              </div>
              
              <button 
                type="submit" 
                className="btn btn-primary" 
                style={{ alignSelf: "flex-end", display: "flex", alignItems: "center", gap: "8px" }}
                disabled={loading}
              >
                {loading ? "⏳ Sedang Mengirim..." : <>📢 Kirim Pengumuman</>}
              </button>
            </form>
          </div>
        )}
      </main>

      {/* TOAST SYSTEM */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            <span>{t.message}</span>
          </div>
        ))}
      </div>

      {/* MODALS */}
      {modalType && (
        <div className="modal-overlay">
          {/* MODAL: ADD CATEGORY */}
          {modalType === "add_category" && (
            <div className="modal-content">
              <div className="modal-header">
                <h3 className="modal-title">Tambah Kategori Baru</h3>
                <button className="modal-close" onClick={() => setModalType(null)}><X size={20} /></button>
              </div>
              <form onSubmit={handleAddCategory}>
                <div className="modal-body">
                  <div className="form-group">
                    <label className="form-label">Nama Kategori</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="Contoh: Akun Premium"
                      value={categoryName}
                      onChange={(e) => {
                        setCategoryName(e.target.value);
                        setCategorySlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-"));
                      }}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Slug Kategori (URL friendly)</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="Contoh: akun-premium"
                      value={categorySlug}
                      onChange={(e) => setCategorySlug(e.target.value.replace(/[^a-z0-9\-]+/g, ""))}
                      required
                    />
                  </div>
                </div>
                <div className="modal-footer">
                  <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Batal</button>
                  <button type="submit" className="btn btn-primary">Tambah</button>
                </div>
              </form>
            </div>
          )}

          {/* MODAL: ADD / EDIT PRODUCT */}
          {(modalType === "add_product" || modalType === "edit_product") && (
            <div className="modal-content">
              <div className="modal-header">
                <h3 className="modal-title">{modalType === "add_product" ? "Tambah Produk Baru" : "Edit Produk"}</h3>
                <button className="modal-close" onClick={() => setModalType(null)}><X size={20} /></button>
              </div>
              <form onSubmit={handleProductSubmit}>
                <div className="modal-body">
                  <div className="form-group">
                    <label className="form-label">Nama Produk</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="Contoh: Spotify Premium 1 Bulan"
                      value={productName}
                      onChange={(e) => setProductName(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Kategori</label>
                    <select
                      className="form-select"
                      value={productCategoryId}
                      onChange={(e) => setProductCategoryId(e.target.value)}
                      required
                    >
                      <option value="">-- Pilih Kategori --</option>
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Harga (Rupiah)</label>
                    <input
                      type="number"
                      className="form-input"
                      placeholder="Contoh: 15000"
                      value={productPrice}
                      onChange={(e) => setProductPrice(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Deskripsi Produk</label>
                    <textarea
                      className="form-textarea"
                      placeholder="Tuliskan info detail cara penggunaan / garansi produk"
                      value={productDescription}
                      onChange={(e) => setProductDescription(e.target.value)}
                    />
                  </div>
                  <div className="form-group" style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <input
                      type="checkbox"
                      id="prod_active_check"
                      checked={productActive}
                      onChange={(e) => setProductActive(e.target.checked)}
                      style={{ width: "18px", height: "18px", accentColor: "var(--accent-purple)" }}
                    />
                    <label htmlFor="prod_active_check" className="form-label" style={{ margin: 0, cursor: "pointer" }}>
                      Tampilkan Produk di Bot (Aktif)
                    </label>
                  </div>
                </div>
                <div className="modal-footer">
                  <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Batal</button>
                  <button type="submit" className="btn btn-primary">{modalType === "add_product" ? "Tambah" : "Simpan"}</button>
                </div>
              </form>
            </div>
          )}

          {/* MODAL: MANAGE STOCK */}
          {modalType === "manage_stock" && selectedProduct && (
            <div className="modal-content" style={{ width: "650px" }}>
              <div className="modal-header">
                <h3 className="modal-title">Kelola Stok: {selectedProduct.name}</h3>
                <button className="modal-close" onClick={() => setModalType(null)}><X size={20} /></button>
              </div>
              <div className="modal-body" style={{ maxHeight: "70vh", overflowY: "auto" }}>
                {/* Add stock form */}
                <form onSubmit={handleAddStock} style={{ marginBottom: "24px", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "20px" }}>
                  <div className="form-group">
                    <label className="form-label">Input Data Stok Baru (Bulk Import)</label>
                    <textarea
                      className="form-textarea"
                      placeholder="Masukkan kredensial/token produk, satu data per baris.&#10;Contoh:&#10;user1@gmail.com:pass123&#10;user2@gmail.com:pass567"
                      value={bulkStockText}
                      onChange={(e) => setBulkStockText(e.target.value)}
                      required
                    />
                    <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Bot akan mengirimkan satu baris data ini ke pembeli saat pembayaran sukses.</span>
                  </div>
                  <button type="submit" className="btn btn-primary btn-sm" style={{ float: "right" }}>
                    <Plus size={12} /> Impor Stok
                  </button>
                  <div style={{ clear: "both" }} />
                </form>

                {/* Stock lists table */}
                <h4 style={{ fontSize: "14px", fontWeight: "600", marginBottom: "12px" }}>Daftar Item Stok</h4>
                <div style={{ overflowX: "auto", border: "1px solid var(--card-border)", borderRadius: "12px" }}>
                  <table className="data-table" style={{ fontSize: "13px" }}>
                    <thead>
                      <tr>
                        <th>Isi Akun / Token</th>
                        <th>Status</th>
                        <th>Aksi</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stockItems.map((item) => (
                        <tr key={item.id}>
                          <td style={{ fontFamily: "monospace", wordBreak: "break-all" }}>{item.content}</td>
                          <td>
                            <span className={`badge badge-${item.is_sold ? "expired" : "completed"}`}>
                              {item.is_sold ? "Terjual" : "Tersedia"}
                            </span>
                          </td>
                          <td>
                            {!item.is_sold && (
                              <button className="btn btn-danger btn-sm" style={{ padding: "4px 8px" }} onClick={() => handleDeleteStockItem(item.id)}>
                                <Trash2 size={12} /> Hapus
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                      {stockItems.length === 0 && (
                        <tr>
                          <td colSpan="3" style={{ textAlign: "center", color: "var(--text-muted)", padding: "20px" }}>Belum ada stok. Silakan masukkan data di atas.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Tutup</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
