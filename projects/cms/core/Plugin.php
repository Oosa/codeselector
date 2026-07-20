<?php

namespace CMS\Core;

use CMS\Contracts\PluginInterface;
use CMS\Events\PluginActivated;
use CMS\Events\PluginDeactivated;

abstract class Plugin implements PluginInterface
{
    protected string $name;
    protected string $version;
    protected string $description = '';
    protected string $author      = '';
    protected array  $hooks       = [];
    protected array  $settings    = [];

    private bool $active = false;

    public function __construct(string $name, string $version)
    {
        $this->name    = $name;
        $this->version = $version;
    }

    abstract public function boot(): void;
    abstract public function install(): void;
    abstract public function uninstall(): void;

    public function activate(): void
    {
        if ($this->active) return;
        $this->active = true;
        $this->registerHooks();
        event(new PluginActivated($this));
    }

    public function deactivate(): void
    {
        $this->active = false;
        $this->unregisterHooks();
        event(new PluginDeactivated($this));
    }

    public function isActive(): bool
    {
        return $this->active;
    }

    public function getName(): string    { return $this->name; }
    public function getVersion(): string { return $this->version; }

    protected function registerHooks(): void
    {
        foreach ($this->hooks as $event => $callback) {
            add_hook($event, [$this, $callback]);
        }
    }

    protected function unregisterHooks(): void
    {
        foreach ($this->hooks as $event => $callback) {
            remove_hook($event, [$this, $callback]);
        }
    }

    protected function addSetting(string $key, mixed $default): void
    {
        $this->settings[$key] = $default;
    }

    public function getSetting(string $key, mixed $fallback = null): mixed
    {
        return $this->settings[$key] ?? $fallback;
    }

    public function updateSetting(string $key, mixed $value): void
    {
        $this->settings[$key] = $value;
    }
}

class PluginManager
{
    private static ?self $instance = null;
    private array $plugins = [];
    private array $registry = [];

    private function __construct() {}

    public static function getInstance(): self
    {
        if (self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    public function register(Plugin $plugin): void
    {
        $name = $plugin->getName();
        if (isset($this->registry[$name])) {
            throw new \RuntimeException("Plugin '$name' already registered");
        }
        $this->registry[$name] = $plugin;
    }

    public function activate(string $name): bool
    {
        $plugin = $this->find($name);
        if (!$plugin) return false;
        $plugin->activate();
        $plugin->boot();
        $this->plugins[$name] = $plugin;
        return true;
    }

    public function deactivate(string $name): bool
    {
        $plugin = $this->find($name);
        if (!$plugin) return false;
        $plugin->deactivate();
        unset($this->plugins[$name]);
        return true;
    }

    public function find(string $name): ?Plugin
    {
        return $this->registry[$name] ?? null;
    }

    public function active(): array
    {
        return array_values($this->plugins);
    }

    public function all(): array
    {
        return array_values($this->registry);
    }

    public function isActive(string $name): bool
    {
        return isset($this->plugins[$name]);
    }

    private function resolveOrder(array $plugins): array
    {
        // Topological sort for dependency resolution
        $sorted = [];
        $visited = [];

        $visit = function (string $name) use (&$visit, &$sorted, &$visited, $plugins): void {
            if (in_array($name, $visited)) return;
            $visited[] = $name;
            $sorted[]  = $name;
        };

        foreach (array_keys($plugins) as $name) {
            $visit($name);
        }
        return $sorted;
    }
}
