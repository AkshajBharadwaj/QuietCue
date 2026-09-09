import SwiftUI

enum MainTab: String, CaseIterable {
    case home, profiles, places, memory

    var label: String {
        switch self {
        case .home: return "Home"
        case .profiles: return "Profiles"
        case .places: return "Places"
        case .memory: return "My context"
        }
    }

    var symbol: String {
        switch self {
        case .home: return "house.fill"
        case .profiles: return "slider.horizontal.3"
        case .places: return "mappin"
        case .memory: return "person.crop.circle.fill"
        }
    }
}

enum Route: Equatable {
    case profileEditor(AlertProfile)
    case profileAgent
    case soundEnrollment(suggestedName: String)
    case speechSettings
    case identity
    case person(PersonMemory?)
    case context(ContextMemory?)
}

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var colorScheme
    @AppStorage("quietcue.selectedTab") private var selectedTabName = MainTab.home.rawValue
    @State private var route: Route? = nil

    private var scheme: MaterialScheme { colorScheme == .dark ? .dark : .light }
    private var selectedTab: MainTab { MainTab(rawValue: selectedTabName) ?? .home }

    var body: some View {
        ZStack {
            scheme.background.ignoresSafeArea()
            if let route {
                routeView(route)
                    .transition(.move(edge: .trailing))
            } else {
                mainScaffold
            }
            snackbar
        }
        .environment(\.scheme, scheme)
        .animation(.easeInOut(duration: 0.2), value: route)
        .onAppear { model.start() }
    }

    private var mainScaffold: some View {
        VStack(spacing: 0) {
            HStack {
                Text("QuietCue").font(MaterialType.titleLarge).foregroundStyle(scheme.onSurface)
                Spacer()
            }
            .padding(.horizontal, 16)
            .frame(height: 64)
            Group {
                switch selectedTab {
                case .home:
                    DashboardView()
                case .profiles:
                    ProfilesView(
                        onEdit: { route = .profileEditor($0) },
                        onGenerateFromText: { route = .profileAgent },
                        onEnrollSound: { route = .soundEnrollment(suggestedName: "") }
                    )
                case .places:
                    SmartPlacesView()
                case .memory:
                    MemoryBankView(
                        onEditSpeech: { route = .speechSettings },
                        onEditIdentity: { route = .identity },
                        onEditPerson: { route = .person($0) },
                        onEditContext: { route = .context($0) }
                    )
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            navigationBar
        }
        .overlay(alignment: .bottomTrailing) {
            if selectedTab == .profiles {
                Button {
                    let template = model.catalog.activeProfile ?? ProfileDefaults.all()[0]
                    var profile = ProfileDefaults.newCustom(template: template)
                    profile.soundRules = ProfileDefaults.completeRules(template.soundRules, soundLibrary: model.catalog.soundLibrary)
                    route = .profileEditor(profile)
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "plus").font(.system(size: 22))
                        Text("New profile").font(MaterialType.labelLarge)
                    }
                    .padding(.horizontal, 20)
                    .frame(height: 56)
                    .foregroundStyle(scheme.onPrimaryContainer)
                    .background(scheme.primaryContainer)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .shadow(color: .black.opacity(0.18), radius: 6, y: 3)
                }
                .buttonStyle(.plain)
                .padding(.trailing, 16)
                .padding(.bottom, 96)
            }
        }
    }

    private var navigationBar: some View {
        HStack(spacing: 0) {
            ForEach(MainTab.allCases, id: \.self) { tab in
                Button {
                    selectedTabName = tab.rawValue
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: tab.symbol)
                            .font(.system(size: 22))
                            .frame(width: 64, height: 32)
                            .foregroundStyle(selectedTab == tab ? scheme.onSecondaryContainer : scheme.onSurfaceVariant)
                            .background(selectedTab == tab ? scheme.secondaryContainer : Color.clear)
                            .clipShape(Capsule())
                        Text(tab.label)
                            .font(MaterialType.labelMedium)
                            .foregroundStyle(selectedTab == tab ? scheme.onSurface : scheme.onSurfaceVariant)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 12)
                    .padding(.bottom, 16)
                }
                .buttonStyle(.plain)
            }
        }
        .background(scheme.surfaceContainer)
    }

    @ViewBuilder
    private func routeView(_ route: Route) -> some View {
        switch route {
        case .profileEditor(let profile):
            ProfileEditorView(
                initialProfile: profile,
                soundLibrary: model.catalog.soundLibrary,
                onBack: { self.route = nil },
                onSave: { saved in
                    model.save(saved)
                    self.route = nil
                }
            )
        case .profileAgent:
            ProfileAgentView(
                activeProfile: model.catalog.activeProfile ?? ProfileDefaults.all()[0],
                soundLibrary: model.catalog.soundLibrary,
                onBack: { self.route = nil },
                onReview: { self.route = .profileEditor($0) }
            )
        case .soundEnrollment(let suggestedName):
            SoundEnrollmentView(
                initialName: suggestedName,
                initialDescription: suggestedName.isEmpty ? "" : "Recurring sound QuietCue classified as \(suggestedName)",
                onBack: { self.route = nil },
                onEnroll: { sound in
                    model.enrollSound(sound)
                    self.route = nil
                }
            )
        case .speechSettings:
            SpeechSettingsView(
                initial: model.memoryBank.speechSettings,
                identityAvailable: model.memoryBank.identity != nil,
                onBack: { self.route = nil },
                onSave: { settings in
                    model.saveSpeechSettings(settings)
                    self.route = nil
                }
            )
        case .identity:
            IdentityEnrollmentView(
                initial: model.memoryBank.identity,
                onBack: { self.route = nil },
                onSave: { identity in
                    model.saveIdentity(identity)
                    self.route = nil
                }
            )
        case .person(let person):
            PersonMemoryEditorView(
                initial: person,
                onBack: { self.route = nil },
                onSave: { saved in
                    model.savePerson(saved)
                    self.route = nil
                }
            )
        case .context(let context):
            ContextMemoryEditorView(
                initial: context,
                onBack: { self.route = nil },
                onSave: { saved in
                    model.saveContext(saved)
                    self.route = nil
                }
            )
        }
    }

    @ViewBuilder
    private var snackbar: some View {
        if let message = model.message {
            VStack {
                Spacer()
                SnackbarM(text: message)
                    .padding(.bottom, route == nil ? 92 : 24)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .task(id: message) {
                        try? await Task.sleep(for: .seconds(3))
                        if model.message == message { model.clearMessage() }
                    }
            }
            .animation(.easeInOut, value: model.message)
        }
    }
}
