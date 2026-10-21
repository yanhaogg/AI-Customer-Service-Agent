import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

// ---------- 用户端页面 ----------
import Home from '../pages/Home'
import Products from '../pages/Products'
import ProductDetail from '../pages/ProductDetail'
import Cart from '../pages/Cart'
import Checkout from '../pages/Checkout'
import Orders from '../pages/Orders'
import OrderDetail from '../pages/OrderDetail'
import Addresses from '../pages/Addresses'
import Profile from '../pages/Profile'
import Chat from '../pages/Chat'
import BrowsingHistory from '../pages/BrowsingHistory'

// ---------- 认证页面 ----------
import Login from '../pages/Login'
import Register from '../pages/Register'

// ---------- 管理 / 客服端页面 ----------
import AdminHomepage from '../pages/AdminHomepage'
import AdminProducts from '../pages/AdminProducts'
import SupportTasks from '../pages/SupportTasks'
import HumanSupport from '../pages/HumanSupport'

export default function Router() {
  return (
    <BrowserRouter>
      <Routes>
        {/* ===== 重定向 ===== */}
        <Route path="/" element={<Navigate to="/home" replace />} />
        <Route path="*" element={<Navigate to="/home" replace />} />

        {/* ===== 用户端 ===== */}
        <Route path="/home" element={<Home />} />
        <Route path="/products" element={<Products />} />
        <Route path="/products/:id" element={<ProductDetail />} />
        <Route path="/cart" element={<Cart />} />
        <Route path="/checkout" element={<Checkout />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/orders/:id" element={<OrderDetail />} />
        <Route path="/addresses" element={<Addresses />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/history" element={<BrowsingHistory />} />

        {/* ===== 认证 ===== */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* ===== 智能客服 ===== */}
        <Route path="/chat" element={<Chat />} />

        {/* ===== 管理端 ===== */}
        <Route path="/admin/homepage" element={<AdminHomepage />} />
        <Route path="/admin/products" element={<AdminProducts />} />
        <Route path="/admin/orders" element={<Orders admin />} />

        {/* ===== 人工客服 / 任务 ===== */}
        <Route path="/admin/tasks" element={<SupportTasks />} />
        <Route path="/admin/support" element={<HumanSupport />} />
      </Routes>
    </BrowserRouter>
  )
}
