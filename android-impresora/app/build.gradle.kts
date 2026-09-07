plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "pe.fonda.impresora"
    compileSdk = 34

    defaultConfig {
        applicationId = "pe.fonda.impresora"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            // Prototipo: firmado con la llave debug para que el APK sea
            // instalable directo en la tablet (sin Play Store).
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

// Sin dependencias: HttpURLConnection, Socket y org.json vienen con Android.
dependencies {}
