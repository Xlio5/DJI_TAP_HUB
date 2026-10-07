package com.tunnathub.app;

public final class AutoStartPolicyTest {
    public static void main(String[] args) {
        matchesOnlyTunNatHubUsbDevice();
        startsOnlyFromBootUsbAttachOrPermissionGrant();
        waitsForPermissionOnlyOnTunNatHubDevice();
        startsFromPermissionCallbackOnlyForGrantedTunNatHubDevice();
        keepsBootScanInsideBroadcastAsyncBudget();
    }

    private static void matchesOnlyTunNatHubUsbDevice() {
        assertTrue(AutoStartPolicyKt.isTunNatHubUsbDeviceForTest(0x0BDA, 0x8812), "matching vid/pid");
        assertFalse(AutoStartPolicyKt.isTunNatHubUsbDeviceForTest(0x2207, 0x0010), "old gadget vid/pid");
        assertFalse(AutoStartPolicyKt.isTunNatHubUsbDeviceForTest(0x0BDA, 0x0001), "same vendor wrong product");
    }

    private static void startsOnlyFromBootUsbAttachOrPermissionGrant() {
        assertTrue(AutoStartPolicyKt.shouldTryAutoStartForTest("android.intent.action.BOOT_COMPLETED"), "boot starts");
        assertTrue(AutoStartPolicyKt.shouldTryAutoStartForTest("android.hardware.usb.action.USB_DEVICE_ATTACHED"), "attach starts");
        assertTrue(AutoStartPolicyKt.shouldTryAutoStartForTest(AutoStartPolicy.USB_PERMISSION_ACTION), "permission starts");
        assertFalse(AutoStartPolicyKt.shouldTryAutoStartForTest("android.hardware.usb.action.USB_DEVICE_DETACHED"), "detach does not start");
    }

    private static void waitsForPermissionOnlyOnTunNatHubDevice() {
        assertTrue(AutoStartPolicyKt.shouldRequestUsbPermissionForTest(0x0BDA, 0x8812, false), "matching device without permission");
        assertFalse(AutoStartPolicyKt.shouldRequestUsbPermissionForTest(0x0BDA, 0x8812, true), "matching device with permission");
        assertFalse(AutoStartPolicyKt.shouldRequestUsbPermissionForTest(0x2207, 0x0010, false), "nonmatching device");
    }

    private static void startsFromPermissionCallbackOnlyForGrantedTunNatHubDevice() {
        assertTrue(AutoStartPolicyKt.shouldStartFromUsbPermissionForTest(0x0BDA, 0x8812, true), "granted matching callback");
        assertFalse(AutoStartPolicyKt.shouldStartFromUsbPermissionForTest(0x0BDA, 0x8812, false), "denied matching callback");
        assertFalse(AutoStartPolicyKt.shouldStartFromUsbPermissionForTest(0x2207, 0x0010, true), "granted nonmatching callback");
        assertFalse(AutoStartPolicyKt.shouldStartFromUsbPermissionForTest(null, null, true), "missing callback device");
    }

    private static void keepsBootScanInsideBroadcastAsyncBudget() {
        assertTrue(
            AutoStartPolicy.INSTANCE.bootScanBudgetMs() < AutoStartPolicy.BROADCAST_ASYNC_BUDGET_MS,
            "boot scan budget"
        );
    }

    private static void assertTrue(boolean actual, String name) {
        if (!actual) throw new AssertionError(name + " expected=true actual=false");
    }

    private static void assertFalse(boolean actual, String name) {
        if (actual) throw new AssertionError(name + " expected=false actual=true");
    }
}
