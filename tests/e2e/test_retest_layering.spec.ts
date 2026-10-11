import { test, expect } from '@playwright/test';

/**
 * Retest Layering Execution Engine & UI Parameter System Test Suite
 * Validates dynamic DOM rendering, single switch toggle, and clean serialization.
 */

test.describe('Retest Layering Execution Engine & UI Parameter System', () => {

    test('1. Retest Layering Single Switch Card Rendering & Toggle', async ({ page }) => {
        // Navigate to Backtest Edit Parameters Modal / Page
        await page.goto('/backtest/14/edit-modal/');

        const layeringToggle = page.locator('#edit_enable_retest_layering');
        await expect(layeringToggle).toBeVisible();

        // Check badge and description
        const badge = page.locator('text=Auto-Adaptive (OTE & Swing High Anchor)');
        await expect(badge).toBeVisible();

        const desc = page.locator('text=Automatically scales limit orders into institutional Fibonacci retest zones');
        await expect(desc).toBeVisible();

        // Ensure toggle can be checked and unchecked cleanly
        if (!await layeringToggle.isChecked()) {
            await layeringToggle.check();
            expect(await layeringToggle.isChecked()).toBeTruthy();
        } else {
            await layeringToggle.uncheck();
            expect(await layeringToggle.isChecked()).toBeFalsy();
            await layeringToggle.check();
            expect(await layeringToggle.isChecked()).toBeTruthy();
        }
    });

    test('2. Clean Form Submission With Zero Complex Alerts', async ({ page }) => {
        await page.goto('/backtest/14/edit-modal/');

        const layeringToggle = page.locator('#edit_enable_retest_layering');
        if (!await layeringToggle.isChecked()) {
            await layeringToggle.check();
        }

        // Form submits successfully without blocking alerts
        let alertTriggered = false;
        page.on('dialog', async dialog => {
            alertTriggered = true;
            await dialog.accept();
        });

        const submitBtn = page.locator("button[type='submit']").first();
        await submitBtn.click();
        expect(alertTriggered).toBeFalsy();
    });

});
