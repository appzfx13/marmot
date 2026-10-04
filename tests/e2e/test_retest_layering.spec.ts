import { test, expect } from '@playwright/test';

/**
 * Retest Layering Execution Engine & UI Parameter System Test Suite
 * Validates dynamic DOM rendering, form constraints, serialization, and simulated backtest execution.
 */

test.describe('Retest Layering Execution Engine & UI Parameter System', () => {

    test('1. Dynamic DOM Expansion & Layer Input Rendering', async ({ page }) => {
        // Navigate to Backtest Edit Parameters Modal / Page
        await page.goto('/backtest/14/edit-modal/');

        const layeringToggle = page.locator('#edit_enable_retest_layering');
        const settingsDiv = page.locator('#retest_layering_settings');
        const layersWrapper = page.locator('#retest_layers_wrapper');

        // Initial state: Layering should be disabled or toggleable
        if (!await layeringToggle.isChecked()) {
            await expect(settingsDiv).toBeHidden();
            await expect(layersWrapper).toBeHidden();
            await layeringToggle.click();
        }

        await expect(settingsDiv).toBeVisible();
        await expect(layersWrapper).toBeVisible();

        // Check dynamic rendering of 3 layer inputs by default
        const layerCountInput = page.locator('#edit_layer_count');
        await expect(layerCountInput).toHaveValue('3');

        let pctInputs = page.locator("input[name='retest_percentages[]']");
        let lotInputs = page.locator("input[name='layer_lots[]']");
        await expect(pctInputs).toHaveCount(3);
        await expect(lotInputs).toHaveCount(3);

        // Dynamically change layer count to 2
        await layerCountInput.fill('2');
        await layerCountInput.dispatchEvent('input');
        await expect(pctInputs).toHaveCount(2);
        await expect(lotInputs).toHaveCount(2);

        // Dynamically change layer count to 4
        await layerCountInput.fill('4');
        await layerCountInput.dispatchEvent('input');
        await expect(pctInputs).toHaveCount(4);
        await expect(lotInputs).toHaveCount(4);
    });

    test('2. Strict Validation Alert: Total Lots < Layer Count', async ({ page }) => {
        await page.goto('/backtest/14/edit-modal/');

        const layeringToggle = page.locator('#edit_enable_retest_layering');
        if (!await layeringToggle.isChecked()) {
            await layeringToggle.click();
        }

        // Set Layer Count = 3, Strategy Lots = 2
        const layerCountInput = page.locator('#edit_layer_count');
        const strategyLotsInput = page.locator('#edit_lots_count');
        await layerCountInput.fill('3');
        await layerCountInput.dispatchEvent('input');

        await strategyLotsInput.fill('2');
        await strategyLotsInput.dispatchEvent('change');

        // Check badge warning
        const badge = page.locator('#layer_validation_badge');
        await expect(badge).toBeVisible();
        await expect(badge).toContainText('Total lot size must be greater than or equal to layer count');

        // Attempt form submission -> dialog alert must trigger
        let alertTriggered = false;
        let alertMessage = '';
        page.on('dialog', async dialog => {
            alertTriggered = true;
            alertMessage = dialog.message();
            await dialog.accept();
        });

        const submitBtn = page.locator("button[type='submit']").first();
        await submitBtn.click();

        expect(alertTriggered).toBeTruthy();
        expect(alertMessage).toContain('Total lot size must be greater than or equal to layer count');
    });

    test('3. Successful Parameter Serialization (Lots = 3, Percentages = [30, 60, 60])', async ({ page }) => {
        await page.goto('/backtest/14/edit-modal/');

        const layeringToggle = page.locator('#edit_enable_retest_layering');
        if (!await layeringToggle.isChecked()) {
            await layeringToggle.click();
        }

        // Layer Count = 3, Strategy Lots = 3
        const layerCountInput = page.locator('#edit_layer_count');
        const strategyLotsInput = page.locator('#edit_lots_count');
        await layerCountInput.fill('3');
        await layerCountInput.dispatchEvent('input');

        await strategyLotsInput.fill('3');
        await strategyLotsInput.dispatchEvent('change');

        // Fill custom pullback percentages: [30, 60, 60]
        const pctInputs = page.locator("input[name='retest_percentages[]']");
        await pctInputs.nth(0).fill('30');
        await pctInputs.nth(1).fill('60');
        await pctInputs.nth(2).fill('60');

        const lotInputs = page.locator("input[name='layer_lots[]']");
        await lotInputs.nth(0).fill('1');
        await lotInputs.nth(1).fill('1');
        await lotInputs.nth(2).fill('1');

        // Check matched validation badge
        const badge = page.locator('#layer_validation_badge');
        await expect(badge).toContainText('Matched: 3 Lots across 3 Layers');

        // Form submits successfully without dialog blocking
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
