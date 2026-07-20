<?php

namespace App\Controllers;

use App\Models\Product;
use App\Services\ProductService;
use App\Services\AuthService;
use App\Http\Request;
use App\Http\Response;
use App\Exceptions\NotFoundException;
use App\Exceptions\ValidationException;

/**
 * Handles HTTP requests for product resources.
 */
class ProductController
{
    private ProductService $productService;
    private AuthService $authService;

    public function __construct(ProductService $productService, AuthService $authService)
    {
        $this->productService = $productService;
        $this->authService    = $authService;
    }

    public function index(Request $request): Response
    {
        $page     = (int) $request->query('page', 1);
        $pageSize = (int) $request->query('page_size', 20);
        $category = $request->query('category');

        $products = $this->productService->list($page, $pageSize, $category);
        return Response::json(['products' => $products, 'page' => $page]);
    }

    public function show(Request $request, int $id): Response
    {
        $product = $this->productService->findById($id);
        if (!$product) {
            throw new NotFoundException("Product $id not found");
        }
        return Response::json($product->toArray());
    }

    public function store(Request $request): Response
    {
        $this->authService->requireAdmin($request);
        $data = $request->validate([
            'name'     => 'required|string|max:200',
            'sku'      => 'required|string|max:50',
            'price'    => 'required|numeric|min:0',
            'category' => 'required|string',
        ]);
        $product = $this->productService->create($data);
        return Response::json($product->toArray(), 201);
    }

    public function update(Request $request, int $id): Response
    {
        $this->authService->requireAdmin($request);
        $product = $this->productService->findById($id);
        if (!$product) {
            throw new NotFoundException("Product $id not found");
        }
        $data = $request->only(['name', 'price', 'stock', 'is_active']);
        $updated = $this->productService->update($product, $data);
        return Response::json($updated->toArray());
    }

    public function destroy(Request $request, int $id): Response
    {
        $this->authService->requireAdmin($request);
        $product = $this->productService->findById($id);
        if (!$product) {
            throw new NotFoundException("Product $id not found");
        }
        $this->productService->delete($product);
        return Response::json(['deleted' => $id], 204);
    }

    public function search(Request $request): Response
    {
        $query   = $request->query('q', '');
        $filters = $request->only(['category', 'min_price', 'max_price', 'in_stock']);
        $results = $this->productService->search($query, $filters);
        return Response::json(['results' => $results, 'count' => count($results)]);
    }

    private function _validatePrice(float $price): bool
    {
        return $price >= 0 && $price <= 99999.99;
    }

    private function _applyDiscount(Product $product, float $pct): Product
    {
        $product->discount_pct = $pct;
        return $product;
    }
}
