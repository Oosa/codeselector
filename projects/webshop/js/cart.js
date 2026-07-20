/**
 * Shopping cart module — client-side logic.
 */

const TAX_RATE = 0.20;
const FREE_SHIPPING_THRESHOLD = 50;
const SHIPPING_COST = 4.99;

class Cart {
    constructor() {
        this.items = [];
        this._coupon = null;
        this._discountPct = 0;
    }

    addItem(product, quantity = 1) {
        const existing = this.items.find(i => i.id === product.id);
        if (existing) {
            existing.quantity += quantity;
        } else {
            this.items.push({ ...product, quantity });
        }
        this._save();
    }

    removeItem(productId) {
        this.items = this.items.filter(i => i.id !== productId);
        this._save();
    }

    applyCoupon(code, discountPct) {
        this._coupon = code;
        this._discountPct = discountPct;
    }

    subtotal() {
        return this.items.reduce((sum, i) => sum + i.price * i.quantity, 0);
    }

    taxAmount() {
        return this.subtotal() * TAX_RATE;
    }

    shippingCost() {
        return this.subtotal() >= FREE_SHIPPING_THRESHOLD ? 0 : SHIPPING_COST;
    }

    discountAmount() {
        return this.subtotal() * (this._discountPct / 100);
    }

    grandTotal() {
        return this.subtotal() + this.taxAmount() + this.shippingCost() - this.discountAmount();
    }

    itemCount() {
        return this.items.reduce((sum, i) => sum + i.quantity, 0);
    }

    isEmpty() {
        return this.items.length === 0;
    }

    clear() {
        this.items = [];
        this._coupon = null;
        this._discountPct = 0;
        this._save();
    }

    _save() {
        localStorage.setItem('cart', JSON.stringify(this.items));
    }

    _load() {
        const raw = localStorage.getItem('cart');
        this.items = raw ? JSON.parse(raw) : [];
    }
}

class CartUI {
    constructor(cart, containerId) {
        this.cart = cart;
        this.container = document.getElementById(containerId);
    }

    render() {
        if (this.cart.isEmpty()) {
            this.container.innerHTML = '<p class="empty-cart">Your cart is empty.</p>';
            return;
        }
        const rows = this.cart.items.map(i => this._renderRow(i)).join('');
        this.container.innerHTML = `<table class="cart-table">${rows}</table>`;
        this._renderSummary();
    }

    _renderRow(item) {
        return `<tr>
          <td>${item.name}</td>
          <td>${item.quantity}</td>
          <td>$${(item.price * item.quantity).toFixed(2)}</td>
        </tr>`;
    }

    _renderSummary() {
        const summary = document.createElement('div');
        summary.className = 'cart-summary';
        summary.innerHTML = `
          <p>Subtotal: $${this.cart.subtotal().toFixed(2)}</p>
          <p>Tax: $${this.cart.taxAmount().toFixed(2)}</p>
          <p>Shipping: $${this.cart.shippingCost().toFixed(2)}</p>
          <p><strong>Total: $${this.cart.grandTotal().toFixed(2)}</strong></p>
        `;
        this.container.appendChild(summary);
    }

    bindEvents() {
        this.container.addEventListener('click', (e) => {
            if (e.target.dataset.remove) {
                this.cart.removeItem(Number(e.target.dataset.remove));
                this.render();
            }
        });
    }
}

async function fetchProductDetails(productId) {
    const response = await fetch(`/api/products/${productId}`);
    if (!response.ok) throw new Error('Product not found');
    return response.json();
}

async function addToCartFromPage(productId, quantity = 1) {
    const product = await fetchProductDetails(productId);
    const cart = new Cart();
    cart._load();
    cart.addItem(product, quantity);
    return cart;
}

export { Cart, CartUI, fetchProductDetails, addToCartFromPage };
