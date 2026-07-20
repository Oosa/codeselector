<?php

namespace App\Services;

use App\Models\Order;
use App\Models\Cart;
use App\Models\User;
use App\Repositories\OrderRepository;
use App\Events\OrderCreated;
use App\Events\OrderShipped;
use App\Exceptions\PaymentException;
use App\Exceptions\StockException;

class OrderService
{
    private OrderRepository $orderRepo;
    private PaymentService $paymentService;
    private StockService $stockService;
    private NotificationService $notifier;

    private const MAX_ITEMS = 50;
    private const MIN_AMOUNT = 1.00;

    public function __construct(
        OrderRepository $orderRepo,
        PaymentService $paymentService,
        StockService $stockService,
        NotificationService $notifier
    ) {
        $this->orderRepo      = $orderRepo;
        $this->paymentService = $paymentService;
        $this->stockService   = $stockService;
        $this->notifier       = $notifier;
    }

    public function createFromCart(Cart $cart, User $user, string $paymentMethod): Order
    {
        $this->validateCart($cart);
        $this->checkStock($cart);

        $order = Order::fromCart($cart, $user, $paymentMethod);
        $this->orderRepo->save($order);

        $this->stockService->reserve($cart);
        event(new OrderCreated($order));

        return $order;
    }

    public function processPayment(Order $order): bool
    {
        try {
            $chargeId = $this->paymentService->charge(
                $order->total(),
                $order->paymentMethod(),
                ['order_id' => $order->id]
            );
            $order->confirm($chargeId);
            $this->orderRepo->save($order);
            $this->notifier->sendConfirmation($order);
            return true;
        } catch (PaymentException $e) {
            $order->cancel('Payment failed: ' . $e->getMessage());
            $this->orderRepo->save($order);
            return false;
        }
    }

    public function ship(Order $order, string $trackingNumber): Order
    {
        $order->ship($trackingNumber);
        $this->orderRepo->save($order);
        $this->notifier->sendShippingUpdate($order);
        event(new OrderShipped($order));
        return $order;
    }

    public function cancel(Order $order, User $user, string $reason = ''): Order
    {
        if (!$this->canCancel($order, $user)) {
            throw new \RuntimeException('Order cannot be cancelled');
        }
        $order->cancel($reason);
        $this->stockService->release($order);
        $this->orderRepo->save($order);
        return $order;
    }

    public function getForUser(User $user, int $page = 1): array
    {
        return $this->orderRepo->findByUser($user->id, $page);
    }

    public function calculateTotals(Cart $cart): array
    {
        $subtotal = $cart->subtotal();
        $tax      = $subtotal * 0.20;
        $shipping = $subtotal >= 50 ? 0.0 : 4.99;
        $total    = $subtotal + $tax + $shipping;

        return compact('subtotal', 'tax', 'shipping', 'total');
    }

    private function validateCart(Cart $cart): void
    {
        if ($cart->isEmpty()) {
            throw new \InvalidArgumentException('Cart is empty');
        }
        if ($cart->itemCount() > self::MAX_ITEMS) {
            throw new \InvalidArgumentException('Too many items in cart');
        }
        if ($cart->subtotal() < self::MIN_AMOUNT) {
            throw new \InvalidArgumentException('Order total too low');
        }
    }

    private function checkStock(Cart $cart): void
    {
        foreach ($cart->items() as $item) {
            if (!$this->stockService->isAvailable($item->productId(), $item->quantity())) {
                throw new StockException("Insufficient stock for product {$item->productId()}");
            }
        }
    }

    private function canCancel(Order $order, User $user): bool
    {
        return $order->isCancellable() &&
               ($order->userId() === $user->id || $user->isAdmin());
    }
}
