#!/bin/sh
# Add SPI NOR flash node to LicheePi Zero Dock DTS
cd /home/xlong/v3s/linux
DTS=arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dts

# Remove trailing newline and append SPI node using sed
sed -i '$a \
\
\/* SPI NOR Flash (w25q128 @ SPI0) *\/\
\&spi0 {\
\t#address-cells = <1>;\
\t#size-cells = <0>;\
\tcs-gpios = <0>; \/* native CS on PC0 *\/\
\tstatus = "okay";\
\
\tflash@0 {\
\t\tcompatible = "jedec,spi-nor";\
\t\treg = <0>;\
\t\t#address-cells = <1>;\
\t\t#size-cells = <1>;\
\t\tlabel = "firmware";\
\t\tspi-max-frequency = <40000000>;\
\t};\
};' $DTS

echo "=== Updated DTS ==="
cat $DTS
