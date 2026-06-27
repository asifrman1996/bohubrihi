// ── Cart State ─────────────────────────────────────────────────
let cart = JSON.parse(localStorage.getItem('bbCart') || '[]');

function saveCart() {
  localStorage.setItem('bbCart', JSON.stringify(cart));
  updateCartUI();
}

function updateCartUI() {
  const count = cart.reduce((s, i) => s + i.qty, 0);
  document.querySelectorAll('.cart-count').forEach(el => {
    el.textContent = count;
    el.style.display = count > 0 ? 'inline-flex' : 'none';
  });
  const total = cart.reduce((s, i) => s + i.price * i.qty, 0);
  const btn = document.getElementById('goCheckoutBtn');
  if (btn) {
    btn.textContent = count > 0
      ? `Checkout (${count} item${count !== 1 ? 's' : ''}) · ৳${total.toFixed(0)}`
      : 'Proceed to Checkout';
  }
  renderCartItems();
}

function addToCart(id, name, price, image, cat, type) {
  type = type || 'product';
  const existing = cart.find(i => i.id === id && (i.type || 'product') === type);
  if (existing) {
    existing.qty++;
  } else {
    cart.push({ id, name, price, image, cat, type, qty: 1 });
  }
  saveCart();
  showCartToast(name);
  openCart();
}

function removeFromCart(id, type) {
  type = type || 'product';
  cart = cart.filter(i => !(i.id === id && (i.type || 'product') === type));
  saveCart();
}

function updateQty(id, delta, type) {
  type = type || 'product';
  const item = cart.find(i => i.id === id && (i.type || 'product') === type);
  if (!item) return;
  item.qty += delta;
  if (item.qty <= 0) cart = cart.filter(i => !(i.id === id && (i.type || 'product') === type));
  saveCart();
}

function renderCartItems() {
  const el = document.getElementById('cartItems');
  if (!el) return;
  if (cart.length === 0) {
    el.innerHTML = `<div class="empty-cart"><div class="icon">🛒</div><p>Your cart is empty</p></div>`;
    document.getElementById('cartTotal').textContent = '0';
    return;
  }
  el.innerHTML = cart.map(item => `
    <div class="cart-item">
      <div class="cart-item-img">${item.image
        ? `<img src="${imageSrc(item.image)}" alt="${item.name}">`
        : getCatIcon(item.cat)}</div>
      <div class="cart-item-info">
        <div class="cart-item-name">${item.name}</div>
        <div class="cart-item-price">${item.price}</div>
        <div class="qty-ctrl">
          <button class="qty-btn" onclick="updateQty(${item.id}, -1, '${item.type || 'product'}')">−</button>
          <span class="qty-num">${item.qty}</span>
          <button class="qty-btn" onclick="updateQty(${item.id}, 1, '${item.type || 'product'}')">+</button>
        </div>
      </div>
      <button class="remove-item" onclick="removeFromCart(${item.id}, '${item.type || 'product'}')" title="Remove">🗑</button>
    </div>
  `).join('');
  const total = cart.reduce((s, i) => s + i.price * i.qty, 0);
  document.getElementById('cartTotal').textContent = total.toFixed(0);
}

function imageSrc(image) {
  if (!image) return '';
  return image.startsWith('http://') || image.startsWith('https://')
    ? image
    : `/static/uploads/${image}`;
}

function getCatIcon(cat) {
  const icons = { 'Soaps': '🧼', 'Face Care': '✨', 'Creams & Lotions': '🧴',
    'Hair Care': '💆', 'Body Care': '🛁', 'Essential Oils': '🌸', 'Gift Sets': '🎁', 'Bundle': '🎁' };
  return icons[cat] || '🌿';
}

// ── Cart Sidebar ───────────────────────────────────────────────
function openCart() {
  document.getElementById('cartSidebar')?.classList.add('open');
  document.getElementById('cartOverlay')?.classList.add('show');
  document.body.style.overflow = 'hidden';
}
function closeCart() {
  document.getElementById('cartSidebar')?.classList.remove('open');
  document.getElementById('cartOverlay')?.classList.remove('show');
  document.body.style.overflow = '';
}

// ── Toast Notification ─────────────────────────────────────────
function showCartToast(name) {
  let toast = document.getElementById('cartToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'cartToast';
    toast.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(80px);
      background:#0f766e;color:#fff;padding:12px 24px;border-radius:100px;font-weight:600;
      font-size:.9rem;z-index:300;transition:transform .3s;white-space:nowrap;`;
    document.body.appendChild(toast);
  }
  toast.textContent = `✓ "${name}" added to cart`;
  toast.style.transform = 'translateX(-50%) translateY(0)';
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { toast.style.transform = 'translateX(-50%) translateY(80px)'; }, 2500);
}

// ── Checkout form: inject cart data ───────────────────────────
function prepareCheckout() {
  if (cart.length === 0) {
    alert('Your cart is empty!');
    return false;
  }
  document.getElementById('cartDataInput').value = JSON.stringify(cart);
  return true;
}

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  updateCartUI();

  document.getElementById('cartOverlay')?.addEventListener('click', closeCart);
  document.getElementById('cartCloseBtn')?.addEventListener('click', closeCart);
  document.getElementById('openCartBtn')?.addEventListener('click', openCart);

  const goCheckout = document.getElementById('goCheckoutBtn');
  if (goCheckout) {
    goCheckout.addEventListener('click', () => {
      if (cart.length === 0) {
        showCartToast('Cart is empty!');
        return;
      }
      closeCart();
      window.location.href = '/checkout';
    });
  }

  // Detail page qty
  const qtyInput = document.getElementById('detailQty');
  if (qtyInput) {
    document.getElementById('detailQtyMinus')?.addEventListener('click', () => {
      if (parseInt(qtyInput.value) > 1) qtyInput.value = parseInt(qtyInput.value) - 1;
    });
    document.getElementById('detailQtyPlus')?.addEventListener('click', () => {
      qtyInput.value = parseInt(qtyInput.value) + 1;
    });
  }

  // Checkout page: build summary
  if (document.getElementById('checkoutSummary')) {
    buildCheckoutSummary();
  }
});

function buildCheckoutSummary() {
  const wrap = document.getElementById('checkoutSummary');
  if (!wrap) return;
  if (cart.length === 0) {
    wrap.innerHTML = '<p style="color:var(--muted);text-align:center;">Cart is empty</p>';
    return;
  }
  let html = '';
  let total = 0;
  cart.forEach(item => {
    const sub = item.price * item.qty;
    total += sub;
    html += `<div class="summary-item"><span>${item.name} × ${item.qty}</span><span>৳${sub.toFixed(0)}</span></div>`;
  });
  html += `<div class="summary-total"><span>Total</span><span class="val">${total.toFixed(0)}</span></div>`;
  wrap.innerHTML = html;
  document.getElementById('cartDataInput').value = JSON.stringify(cart);
}
