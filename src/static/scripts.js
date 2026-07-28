// Shopping Cart State
let cart = [];

document.addEventListener('DOMContentLoaded', () => {
    fetchProducts();
});

// Fetch products from backend API
function fetchProducts() {
    const productGrid = document.getElementById('product-grid');
    
    fetch('/products')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(products => {
            renderProducts(products);
        })
        .catch(error => {
            console.error('Error fetching products:', error);
            productGrid.innerHTML = `<p class="error-msg">Failed to load products. Make sure backend API is running.</p>`;
        });
}

// Render Product Cards into DOM
function renderProducts(products) {
    const productGrid = document.getElementById('product-grid');
    productGrid.innerHTML = '';

    if (!products || products.length === 0) {
        productGrid.innerHTML = '<p>No products available.</p>';
        return;
    }

    products.forEach(product => {
        const card = document.createElement('div');
        card.className = 'product-card';
        card.innerHTML = `
            <div class="product-info">
                <h3>${escapeHtml(product.name)}</h3>
                <p>${escapeHtml(product.description)}</p>
            </div>
            <div class="product-footer">
                <span class="price-tag">$${parseFloat(product.price).toFixed(2)}</span>
                <button class="add-cart-btn" onclick="addToCart(${product.id}, '${escapeJsString(product.name)}', ${product.price})">
                    + Add
                </button>
            </div>
        `;
        productGrid.appendChild(card);
    });
}

// Add Item to Cart
function addToCart(id, name, price) {
    const existing = cart.find(item => item.id === id);
    if (existing) {
        existing.quantity += 1;
    } else {
        cart.push({ id, name, price, quantity: 1 });
    }
    
    updateCartUI();
    showToast(`Added "${name}" to cart!`);
}

// Update Cart Badge, List, and Total
function updateCartUI() {
    const cartItemsContainer = document.getElementById('cart-items');
    const cartCountBadge = document.getElementById('cart-count-badge');
    const cartTotalPrice = document.getElementById('cart-total-price');

    const totalCount = cart.reduce((sum, item) => sum + item.quantity, 0);
    const totalPrice = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);

    cartCountBadge.textContent = totalCount;
    cartTotalPrice.textContent = `$${totalPrice.toFixed(2)}`;

    if (cart.length === 0) {
        cartItemsContainer.innerHTML = '<p class="empty-cart-msg">Your cart is currently empty.</p>';
        return;
    }

    cartItemsContainer.innerHTML = cart.map(item => `
        <div class="cart-item">
            <div>
                <div class="cart-item-title">${escapeHtml(item.name)}</div>
                <div class="cart-item-qty">Qty: ${item.quantity} × $${parseFloat(item.price).toFixed(2)}</div>
            </div>
            <div class="cart-item-price">$${(item.price * item.quantity).toFixed(2)}</div>
        </div>
    `).join('');
}

// Toggle Cart Sidebar Drawer
function toggleCart() {
    const sidebar = document.getElementById('cart-sidebar');
    const overlay = document.getElementById('cart-overlay');
    
    sidebar.classList.toggle('open');
    overlay.classList.toggle('active');
}

// Toast Notifications
function showToast(message) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function checkout() {
    if (cart.length === 0) {
        showToast('Your cart is empty!');
        return;
    }
    alert('Thank you for your order! Checkout simulated successfully.');
    cart = [];
    updateCartUI();
    toggleCart();
}

function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escapeJsString(str) {
    return String(str).replace(/'/g, "\\'");
}
