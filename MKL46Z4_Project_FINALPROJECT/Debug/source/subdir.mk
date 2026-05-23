################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../source/app.c \
../source/main.c \
../source/motor.c \
../source/serial_stream.c 

C_DEPS += \
./source/app.d \
./source/main.d \
./source/motor.d \
./source/serial_stream.d 

OBJS += \
./source/app.o \
./source/main.o \
./source/motor.o \
./source/serial_stream.o 


# Each subdirectory must supply rules for building sources it contributes
source/%.o: ../source/%.c source/subdir.mk
	@echo 'Building file: $<'
	@echo 'Invoking: MCU C Compiler'
	arm-none-eabi-gcc -DCPU_MKL46Z256VLL4_cm0plus -DCPU_MKL46Z256VLL4 -DFSL_RTOS_BM -DSDK_OS_BAREMETAL -DSDK_DEBUGCONSOLE=0 -DCR_INTEGER_PRINTF -DPRINTF_FLOAT_ENABLE=0 -D__MCUXPRESSO -D__USE_CMSIS -DDEBUG -D__REDLIB__ -I"C:\Users\iaaa3\Documents\MCUXpressoIDE_25.6.136\workspace\MKL46Z4_Project_FINALPROJECT\board" -I"C:\Users\iaaa3\Documents\MCUXpressoIDE_25.6.136\workspace\MKL46Z4_Project_FINALPROJECT\source" -I"C:\Users\iaaa3\Documents\MCUXpressoIDE_25.6.136\workspace\MKL46Z4_Project_FINALPROJECT" -I"C:\Users\iaaa3\Documents\MCUXpressoIDE_25.6.136\workspace\MKL46Z4_Project_FINALPROJECT\drivers" -I"C:\Users\iaaa3\Documents\MCUXpressoIDE_25.6.136\workspace\MKL46Z4_Project_FINALPROJECT\CMSIS" -I"C:\Users\iaaa3\Documents\MCUXpressoIDE_25.6.136\workspace\MKL46Z4_Project_FINALPROJECT\startup" -I"C:\Users\iaaa3\Documents\MCUXpressoIDE_25.6.136\workspace\MKL46Z4_Project_FINALPROJECT\utilities" -O0 -fno-common -g3 -gdwarf-4 -Wall -c -ffunction-sections -fdata-sections -fno-builtin -fmerge-constants -fmacro-prefix-map="$(<D)/"= -mcpu=cortex-m0plus -mthumb -D__REDLIB__ -fstack-usage -specs=redlib.specs -MMD -MP -MF"$(@:%.o=%.d)" -MT"$(@:%.o=%.o)" -MT"$(@:%.o=%.d)" -o "$@" "$<"
	@echo 'Finished building: $<'
	@echo ' '


clean: clean-source

clean-source:
	-$(RM) ./source/app.d ./source/app.o ./source/main.d ./source/main.o ./source/motor.d ./source/motor.o ./source/serial_stream.d ./source/serial_stream.o

.PHONY: clean-source

